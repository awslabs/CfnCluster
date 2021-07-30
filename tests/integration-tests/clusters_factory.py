# Copyright 2019 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License").
# You may not use this file except in compliance with the License.
# A copy of the License is located at
#
# http://aws.amazon.com/apache2.0/
#
# or in the "LICENSE.txt" file accompanying this file.
# This file is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, express or implied.
# See the License for the specific language governing permissions and limitations under the License.
import functools
import json
import logging
import re
import subprocess
import time

import boto3
import yaml
from retrying import retry
from utils import (
    dict_add_nested_key,
    get_stack_id_tag_filter,
    retrieve_cfn_outputs,
    retrieve_cfn_parameters,
    retrieve_cfn_resources,
    retry_if_subprocess_error,
    run_command,
)


def suppress_and_log_exception(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logging.error("Failed when running function %s. Ignoring exception. Error: %s", func.__name__, e)

    return wrapper


class Cluster:
    """Contain all static and dynamic data related to a cluster instance."""

    def __init__(self, name, ssh_key, config_file, region):
        self.name = name
        self.config_file = config_file
        self.ssh_key = ssh_key
        self.region = region
        with open(config_file) as conf_file:
            self.config = yaml.safe_load(conf_file)
        self.has_been_deleted = False
        self.create_complete = False
        self.__cfn_parameters = None
        self.__cfn_outputs = None
        self.__cfn_resources = None
        self.__cfn_stack_arn = None

    def __repr__(self):
        attrs = ", ".join(["{key}={value}".format(key=key, value=repr(value)) for key, value in self.__dict__.items()])
        return "{class_name}({attrs})".format(class_name=self.__class__.__name__, attrs=attrs)

    def mark_as_created(self):
        """Mark the cluster as created.

        This is used by some fixtures to know whether to delete log files or not.
        """
        self.create_complete = True

    def update(self, config_file, force=True, extra_args=None, raise_on_error=True, wait=True, log_error=True):
        """
        Update a cluster with an already updated config.
        :param force: if to use --force flag when update
        :param extra_args: list of strings; extra args to pass to `pcluster update-cluster`
        :param raise_on_error: raise exception if cluster creation fails
        :param wait: wait for update completion
        :param log_error: log error when error occurs. This can be set to False when error is expected
        """
        # update the cluster
        logging.info("Updating cluster {0} with config {1}".format(self.name, config_file))
        command = [
            "pcluster",
            "update-cluster",
            "--cluster-configuration",
            config_file,
            "--cluster-name",
            self.name,
        ]
        if wait:
            command.append("--wait")
        if force:
            command.extend(["--force-update", "true"])
        if extra_args:
            command.extend(extra_args)
        result = run_command(command, raise_on_error=raise_on_error, log_error=log_error)
        logging.info("update-cluster response: %s", result.stdout)
        response = json.loads(result.stdout)
        if response.get("cloudFormationStackStatus") != "UPDATE_COMPLETE":
            error = f"Cluster update failed for {self.name}"
            if log_error:
                logging.error(error)
            if raise_on_error:
                raise Exception(error)
        logging.info("Cluster {0} updated successfully".format(self.name))
        # Only update config file attribute if update is successful
        self.config_file = config_file
        with open(self.config_file) as conf_file:
            self.config = yaml.safe_load(conf_file)

        # reset cached properties
        self._reset_cached_properties()

        return response

    def delete(self, delete_logs=False):
        """Delete this cluster."""
        if self.has_been_deleted:
            return
        cmd_args = ["pcluster", "delete-cluster", "--cluster-name", self.name, "--wait"]
        if delete_logs:
            logging.warning("Updating stack %s to delete CloudWatch logs on stack deletion.", self.name)
            try:
                dict_add_nested_key(
                    self.config,
                    False,
                    ("Monitoring", "Logs", "CloudWatch", "RetainOnDelete"),
                )
                with open(self.config_file, "w") as conf_file:
                    yaml.dump(self.config, conf_file)
                self.update(self.config_file, force=True)
            except subprocess.CalledProcessError as e:
                logging.error(
                    "Failed updating cluster to delete log with error:\n%s\nand output:\n%s", e.stderr, e.stdout
                )
                raise
        else:
            logging.warning("CloudWatch logs for cluster %s are preserved due to failure.", self.name)
        try:
            self.cfn_stack_arn  # Cache cfn_stack_arn attribute before stack deletion
            result = run_command(cmd_args, log_error=False)
            if "DELETE_FAILED" in result.stdout:
                error = "Cluster deletion failed for {0} with output: {1}".format(self.name, result.stdout)
                logging.error(error)
                raise Exception(error)
            logging.info("Cluster {0} deleted successfully".format(self.name))
        except subprocess.CalledProcessError as e:
            if re.search(f"Stack with id {self.name} does not exist", e.stdout):
                pass
            else:
                logging.error("Failed destroying cluster with error:\n%s\nand output:\n%s", e.stderr, e.stdout)
                raise
        self.has_been_deleted = True

    def start(self):
        """Run pcluster start and return the result."""
        cmd_args = ["pcluster", "update-compute-fleet", "--cluster-name", self.name, "--status"]
        scheduler = self.config["Scheduling"]["Scheduler"]
        if scheduler == "slurm":
            cmd_args.append("START_REQUESTED")
        elif scheduler == "awsbatch":
            cmd_args.append("ENABLED")
        try:
            result = run_command(cmd_args, log_error=False)
            logging.info("Cluster {0} started successfully".format(self.name))
            return result.stdout
        except subprocess.CalledProcessError as e:
            logging.error("Failed starting cluster with error:\n%s\nand output:\n%s", e.stderr, e.stdout)
            raise

    def stop(self):
        """Run pcluster stop and return the result."""
        cmd_args = ["pcluster", "update-compute-fleet", "--cluster-name", self.name, "--status"]
        scheduler = self.config["Scheduling"]["Scheduler"]
        if scheduler == "slurm":
            cmd_args.append("STOP_REQUESTED")
        elif scheduler == "awsbatch":
            cmd_args.append("DISABLED")
        try:
            result = run_command(cmd_args, log_error=False)
            logging.info("Cluster {0} stopped successfully".format(self.name))
            return result.stdout
        except subprocess.CalledProcessError as e:
            logging.error("Failed stopping cluster with error:\n%s\nand output:\n%s", e.stderr, e.stdout)
            raise

    def describe_cluster(self):
        """Run pcluster describe-cluster and return the result."""
        cmd_args = ["pcluster", "describe-cluster", "--cluster-name", self.name]
        try:
            result = run_command(cmd_args, log_error=False)
            response = json.loads(result.stdout)
            logging.info("Get cluster {0} status successfully".format(self.name))
            return response
        except subprocess.CalledProcessError as e:
            logging.error("Failed when getting cluster status with error:\n%s\nand output:\n%s", e.stderr, e.stdout)
            raise

    def describe_compute_fleet(self):
        """Run pcluster describe-compute-fleet and return the result."""
        cmd_args = ["pcluster", "describe-compute-fleet", "--cluster-name", self.name]
        try:
            result = run_command(cmd_args, log_error=False)
            response = json.loads(result.stdout)
            logging.info("Describe cluster %s compute fleet successfully", self.name)
            return response
        except subprocess.CalledProcessError as e:
            logging.error(
                "Failed when getting cluster compute fleet with error:\n%s\nand output:\n%s", e.stderr, e.stdout
            )
            raise

    def get_cluster_instance_ids(self, node_type=None, queue_name=None):
        """Run pcluster describe-cluster-instances and collect instance ids."""
        cmd_args = ["pcluster", "describe-cluster-instances", "--cluster-name", self.name]
        if node_type:
            if node_type == "HeadNode":
                node_type = "HEAD"
            elif node_type == "Compute":
                node_type = "COMPUTE"
            else:
                raise ValueError
            cmd_args.extend(["--node-type", node_type])
        if queue_name:
            cmd_args.extend(["--queue-name", queue_name])
        try:
            result = run_command(cmd_args, log_error=False)
            response = json.loads(result.stdout)
            logging.info("Get cluster {0} instances successfully".format(self.name))
            return [instance["instanceId"] for instance in response["instances"]]
        except subprocess.CalledProcessError as e:
            logging.error("Failed when getting cluster instances with error:\n%s\nand output:\n%s", e.stderr, e.stdout)
            raise

    def export_logs(self, bucket, output, bucket_prefix=None):
        """Run pcluster export-cluster-logs and return the result."""
        cmd_args = [
            "pcluster",
            "export-cluster-logs",
            "--cluster-name",
            self.name,
            "--bucket",
            bucket,
            "--output",
            output,
        ]
        if bucket_prefix:
            cmd_args += ["--bucket-prefix", bucket_prefix]
        try:
            result = run_command(cmd_args, log_error=False)
            response = json.loads(result.stdout)
            logging.info("Cluster's logs exported successfully")
            return response
        except subprocess.CalledProcessError as e:
            logging.error("Failed exporting cluster's logs with error:\n%s\nand output:\n%s", e.stderr, e.stdout)
            raise

    def list_logs(self):
        """Run pcluster list-cluster-logs and return the result."""
        cmd_args = ["pcluster", "list-cluster-logs", self.name]
        try:
            result = run_command(cmd_args, log_error=False)
            logging.info("Cluster's logs listed successfully")
            return result.stdout
        except subprocess.CalledProcessError as e:
            logging.error("Failed listing cluster's logs with error:\n%s\nand output:\n%s", e.stderr, e.stdout)
            raise

    def get_log_events(self, log_stream, head=None, tail=None):
        """Run pcluster get-cluster-log-events and return the result."""
        cmd_args = ["pcluster", "get-cluster-log-events", self.name, "--log-stream-name", log_stream]
        if head:
            cmd_args += ["--head", str(head)]
        if tail:
            cmd_args += ["--tail", str(tail)]
        try:
            result = run_command(cmd_args, log_error=False)
            logging.info("Log events listed successfully")
            return result.stdout
        except subprocess.CalledProcessError as e:
            logging.error("Failed listing log events with error:\n%s\nand output:\n%s", e.stderr, e.stdout)
            raise

    @property
    def cfn_name(self):
        """Return the name of the CloudFormation stack associated to the cluster."""
        return self.name

    @property
    def head_node_ip(self):
        """Return the public ip of the cluster head node."""
        ec2 = boto3.client("ec2", region_name=self.region)
        filters = [
            {"Name": "tag:parallelcluster:cluster-name", "Values": [self.cfn_name]},
            {"Name": "instance-state-name", "Values": ["running"]},
            {"Name": "tag:parallelcluster:node-type", "Values": ["HeadNode"]},
        ]
        instance = ec2.describe_instances(Filters=filters).get("Reservations")[0].get("Instances")[0]
        return instance.get("PublicIpAddress") if instance.get("PublicIpAddress") else instance.get("PrivateIpAddress")

    @property
    def os(self):
        """Return the os used for the cluster."""
        return self.config["Image"]["Os"]

    @property
    def cfn_parameters(self):
        """
        Return the CloudFormation stack parameters for the cluster.
        Parameters are retrieved only once and then cached.
        """
        if not self.__cfn_parameters:
            self.__cfn_parameters = retrieve_cfn_parameters(self.cfn_name, self.region)
        return self.__cfn_parameters

    @property
    def cfn_outputs(self):
        """
        Return the CloudFormation stack outputs for the cluster.
        Outputs are retrieved only once and then cached.
        """
        if not self.__cfn_outputs:
            self.__cfn_outputs = retrieve_cfn_outputs(self.cfn_name, self.region)
        return self.__cfn_outputs

    @property
    def cfn_resources(self):
        """
        Return the CloudFormation stack resources for the cluster.
        Resources are retrieved only once and then cached.
        """
        if not self.__cfn_resources:
            self.__cfn_resources = retrieve_cfn_resources(self.cfn_name, self.region)
        return self.__cfn_resources

    @property
    def cfn_stack_arn(self):
        """Return CloudFormation stack ARN."""
        if not self.__cfn_stack_arn:
            self.__cfn_stack_arn = boto3.client("cloudformation").describe_stacks(StackName=self.name)["Stacks"][0][
                "StackId"
            ]
        return self.__cfn_stack_arn

    def _reset_cached_properties(self):
        """Discard cached data."""
        self.__cfn_parameters = None
        self.__cfn_outputs = None
        self.__cfn_resources = None

    def delete_resource_by_stack_id_tag(self):
        """Delete resources by stack id tag."""
        self._delete_snapshots()
        self._delete_volumes()

    @suppress_and_log_exception
    def _delete_snapshots(self):
        ec2_client = boto3.client("ec2", region_name=self.region)
        snapshots = ec2_client.describe_snapshots(Filters=[get_stack_id_tag_filter(self.cfn_stack_arn)])["Snapshots"]
        for snapshot in snapshots:
            ec2_client.delete_snapshot(SnapshotId=snapshot["SnapshotId"])

    @suppress_and_log_exception
    def _delete_volumes(self):
        ec2_client = boto3.client("ec2", region_name=self.region)
        volumes = ec2_client.describe_volumes(Filters=[get_stack_id_tag_filter(self.cfn_stack_arn)])["Volumes"]
        for volume in volumes:
            ec2_client.delete_snapshot(VolumeId=volume["VolumeId"])


class ClustersFactory:
    """Manage creation and destruction of pcluster clusters."""

    def __init__(self, delete_logs_on_success=False):
        self.__created_clusters = {}
        self._delete_logs_on_success = delete_logs_on_success

    def create_cluster(self, cluster, extra_args=None, raise_on_error=True, wait=True, log_error=True):
        """
        Create a cluster with a given config.
        :param cluster: cluster to create.
        :param extra_args: list of strings; extra args to pass to `pcluster create`
        :param raise_on_error: raise exception if cluster creation fails
        :param wait: wait for creation completion
        :param log_error: log error when error occurs. This can be set to False when error is expected
        """
        name = cluster.name
        config = cluster.config_file
        if name in self.__created_clusters:
            raise ValueError("Cluster {0} already exists".format(name))

        # create the cluster
        logging.info("Creating cluster {0} with config {1}".format(name, config))
        self.__created_clusters[name] = cluster
        create_cmd_args = [
            "pcluster",
            "create-cluster",
            "--rollback-on-failure",
            "false",
            "--cluster-configuration",
            config,
            "--cluster-name",
            name,
        ]
        if wait:
            create_cmd_args.append("--wait")
        if extra_args:
            create_cmd_args.extend(extra_args)
        result = run_command(create_cmd_args, timeout=7200, raise_on_error=raise_on_error, log_error=log_error)
        logging.info("create-cluster response: %s", result.stdout)
        response = json.loads(result.stdout)
        if wait:
            if response.get("cloudFormationStackStatus") != "CREATE_COMPLETE":
                error = f"Cluster creation failed for {name}"
                logging.error(error)
                if raise_on_error:
                    raise Exception(error)
            else:
                logging.info("Cluster {0} created successfully".format(name))
                cluster.mark_as_created()
            # FIXME: temporary workaround since in certain circumstances the cluster isn't ready for
            # job submission right after creation. We need to investigate this further.
            logging.info("Sleeping for 30 seconds in case cluster is not ready yet")
            time.sleep(30)
        else:
            logging.info("Cluster {0} creation started successfully".format(name))
        return response

    def destroy_cluster(self, name, test_passed):
        """Destroy a created cluster."""
        logging.info("Destroying cluster {0}".format(name))
        if name in self.__created_clusters:
            delete_logs = test_passed and self._delete_logs_on_success and self.__created_clusters[name].create_complete
            try:
                cluster = self.__created_clusters[name]
                cluster.delete(delete_logs=delete_logs)
            except Exception as e:
                logging.error(
                    "Failed when deleting cluster %s with error %s. Retrying deletion without deleting logs.", name, e
                )
                self._destroy_cluster(name)
            finally:
                cluster.delete_resource_by_stack_id_tag()
            del self.__created_clusters[name]
            logging.info("Cluster {0} deleted successfully".format(name))
        else:
            logging.warning("Couldn't find cluster with name {0}. Skipping deletion.".format(name))

    def register_cluster(self, cluster):
        """Register a cluster created externally."""
        self.__created_clusters[cluster.name] = cluster

    @retry(stop_max_attempt_number=5, wait_fixed=5000, retry_on_exception=retry_if_subprocess_error)
    def _destroy_cluster(self, name):
        self.__created_clusters[name].delete(delete_logs=False)

    def destroy_all_clusters(self, test_passed):
        """Destroy all created clusters."""
        logging.debug("Destroying all clusters")
        for key in list(self.__created_clusters.keys()):
            try:
                self.destroy_cluster(key, test_passed)
            except Exception as e:
                logging.error("Failed when destroying cluster {0} with exception {1}.".format(key, e))
