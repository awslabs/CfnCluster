#!/usr/bin/env python2.6

# Copyright 2018 Amazon.com, Inc. or its affiliates. All Rights Reserved.
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
from __future__ import print_function

import datetime
import os
import pipes
import re
import shutil
import sys
import tempfile
import time

import argparse

from awsbatch.common import AWSBatchCliConfig, Boto3ClientFactory, config_logger
from awsbatch.utils import fail, get_job_definition_name_by_arn, shell_join


def _get_parser():
    """
    Parse input parameters and return the ArgumentParser object.

    If the command is executed without the --cluster parameter, the command will use the default cluster_name
    specified in the [main] section of the user's awsbatch-cli.cfg configuration file and will search
    for the [cluster cluster-name] section, if the section doesn't exist, it will ask to CloudFormation
    the required information.

    If the --cluster parameter is set, the command will search for the [cluster cluster-name] section
    in the user's awsbatch-cli.cfg configuration file or, if the file doesn't exist, it will ask to CloudFormation
    the required information.

    :return: the ArgumentParser object
    """
    parser = argparse.ArgumentParser(description="Submits jobs to the cluster's Job Queue.")
    parser.add_argument(
        "-jn",
        "--job-name",
        help="The name of the job. The first character must be alphanumeric, and up to 128 letters "
        "(uppercase and lowercase), numbers, hyphens, and underscores are allowed",
    )
    parser.add_argument("-c", "--cluster", help="Cluster to use")
    parser.add_argument(
        "-cf",
        "--command-file",
        help="Identifies that the command is a file to be transferred to the compute instances",
        action="store_true",
    )
    parser.add_argument(
        "-p",
        "--vcpus",
        help="The number of vCPUs to reserve for the container. When used in conjunction with --nodes it identifies "
        "the number of vCPUs per node. Default is 1",
        type=int,
        default=1,
    )
    parser.add_argument(
        "-m",
        "--memory",
        help="The hard limit (in MiB) of memory to present to the job. If your job attempts to exceed the memory "
        "specified here, the job is killed. Default is 128",
        type=int,
        default=128,
    )
    parser.add_argument(
        "-e",
        "--env",
        help="Comma separated list of environment variable names to export to the Job environment. "
        "Use 'all' to export all the environment variables, except the ones listed to the --env-blacklist parameter "
        "and variables starting with PCLUSTER_* and AWS_BATCH_* prefix.",
    )
    parser.add_argument(
        "-eb",
        "--env-blacklist",
        help="Comma separated list of environment variable names to NOT export to the Job environment. "
        "Default: HOME, PWD, USER, PATH, LD_LIBRARY_PATH, TERM, TERMCAP.",
    )
    parser.add_argument(
        "-r",
        "--retry-attempts",
        help="The number of times to move a job to the RUNNABLE status. You may specify between 1 and 10 attempts. "
        "If the value of attempts is greater than one, the job is retried if it fails until it has moved to RUNNABLE "
        "that many times. Default value is 1",
        type=int,
        default=1,
    )
    parser.add_argument(
        "-t",
        "--timeout",
        help="The time duration in seconds (measured from the job attempt's startedAt timestamp) after which AWS "
        "Batch terminates your jobs if they have not finished. It must be at least 60 seconds",
        type=int,
    )
    # MNP parameter
    parser.add_argument(
        "-n",
        "--nodes",
        help="The number of nodes to reserve for the job. It enables Multi-Node Parallel submission",
        type=int,
    )
    # array parameters
    parser.add_argument(
        "-a",
        "--array-size",
        help="The size of the array. It can be between 2 and 10,000. If you specify array properties for a job, "
        "it becomes an array job",
        type=int,
    )
    parser.add_argument(
        "-d",
        "--depends-on",
        help="A semicolon separated list of dependencies for the job. A job can depend upon a maximum of 20 jobs. "
        "You can specify a SEQUENTIAL type dependency without specifying a job ID for array jobs so that each child "
        "array job completes sequentially, starting at index 0. You can also specify an N_TO_N type dependency "
        "with a job ID for array jobs so that each index child of this job must wait for the corresponding index "
        "child of each dependency to complete before it can begin. Syntax: jobId=<string>,type=<string>;...",
    )
    parser.add_argument("-aws", "--awscli", help=argparse.SUPPRESS, action="store_true")
    parser.add_argument("-ll", "--log-level", help=argparse.SUPPRESS, default="ERROR")
    parser.add_argument(
        "command",
        help="The command to submit (it must be available on the compute instances) "
        "or the file name to be transferred (see --command-file option).",
        default=sys.stdin,
        nargs="?",
    )
    parser.add_argument("arguments", help="Arguments for the command or the command-file (optional).", nargs="*")
    return parser


def _validate_parameters(args):
    """
    Validate input parameters.

    :param args: args variable
    """
    if args.command_file:
        if not type(args.command) == str:
            fail("The command parameter is required with --command-file option")
        elif not os.path.isfile(args.command):
            fail("The command parameter (%s) must be an existing file" % args.command)
    elif not sys.stdin.isatty():
        # stdin
        if args.arguments or type(args.command) == str:
            fail("Error: command and arguments cannot be specified when submitting by stdin.")
    elif not type(args.command) == str:
        fail("Parameters validation error: command parameter is required.")

    if args.depends_on and not re.match(r"(jobId|type)=[^\s,]+([\s,]?(jobId|type)=[^\s]+)*", args.depends_on):
        fail("Parameters validation error: please double check --depends-on parameter syntax.")

    if args.env_blacklist and (not args.env or args.env != "all"):
        fail('--env-blacklist parameter can be used only associated with --env "all"')


def _get_job_folder(job_id):
    """
    Get relative folder path to use for the given job_id.

    :param job_id: the job_id will be the subfolder name
    :return: batch/<job_id>/
    """
    return "batch/{0}/".format(job_id)


class S3Uploader(object):
    """S3 uploader."""

    def __init__(self, boto3_factory, s3_bucket):
        """Constructor.

        :param boto3_factory: initialized Boto3ClientFactory object
        :param s3_bucket: S3 bucket to use
        """
        self.boto3_factory = boto3_factory
        self.s3_bucket = s3_bucket

    def put_file(self, file_path, key_name, timeout):
        """
        Upload a file to an s3 bucket.

        :param file_path: file to upload
        :param key_name: S3 key to create
        :param timeout: S3 expiration time in seconds
        """
        default_expiration = 30  # minutes
        expires = datetime.datetime.now() + datetime.timedelta(minutes=default_expiration)
        if timeout:
            expires += datetime.timedelta(seconds=timeout)

        s3_client = self.boto3_factory.get_client("s3")
        s3_client.upload_file(file_path, self.s3_bucket, key_name, ExtraArgs={"Expires": expires})


def _upload_and_get_command(boto3_factory, args, job_name, config, log):
    """
    Get command by parsing args and config.

    The function will also perform an s3 upload, if needed.
    :param boto3_factory: initialized Boto3ClientFactory object
    :param args: input arguments
    :param job_name: job name
    :param config: config object
    :param log: log
    :return: command to submit
    """
    if args.command_file or not sys.stdin.isatty() or args.env:
        # define job script name
        job_id = "job-{0}-{1}".format(job_name, int(time.time() * 1000))
        job_folder = _get_job_folder(job_id)
        job_script = job_id + ".sh"
        log.info("Using command-file option or stdin. Job script name: %s" % job_script)

        s3_uploader = S3Uploader(boto3_factory, config.s3_bucket)
        env_file = None
        if args.env:
            env_file = job_id + ".env.sh"
            # get environment variables and upload file used to extend the submission environment
            env_blacklist = args.env_blacklist if args.env_blacklist else config.env_blacklist
            _get_env_and_upload(s3_uploader, args.env, env_blacklist, job_folder, env_file, args.timeout, log)

        # upload job script
        if args.command_file:
            # existing script file
            try:
                s3_uploader.put_file(args.command, job_folder + job_script, args.timeout)
            except Exception as e:
                fail("Error creating job script. Failed with exception: %s" % e)
        elif not sys.stdin.isatty():
            # stdin
            _get_stdin_and_upload(s3_uploader, job_folder, job_script, args.timeout)

        # define command to execute
        bash_command = _compose_bash_command(args, config.s3_bucket, config.region, job_folder, job_script, env_file)
        command = ["/bin/bash", "-c", bash_command]
    elif type(args.command) == str:
        log.info("Using command parameter")
        command = [args.command] + args.arguments
    else:
        fail("Unexpected error. Command cannot be empty.")
    log.info("Command: %s" % shell_join(command))
    return command


def _get_stdin_and_upload(s3_uploader, job_folder, job_script, timeout):
    """
    Create file from STDIN and upload to S3.

    :param s3_uploader: S3Uploader object
    :param job_folder: S3 bucket subfolder
    :param job_script: job script name
    :param timeout: S3 expiration time in seconds
    """
    try:
        # copy stdin to temporary file and upload
        with os.fdopen(sys.stdin.fileno(), "rb") as src:
            with tempfile.NamedTemporaryFile() as dst:
                shutil.copyfileobj(src, dst)
                s3_uploader.put_file(dst.name, job_folder + job_script, timeout)
    except Exception as e:
        fail("Error creating job script. Failed with exception: %s" % e)


def _get_env_and_upload(s3_uploader, env, env_blacklist, job_folder, env_file, timeout, log):
    """
    Get environment variables, create a file containing the list of the exported env variables and upload to S3.

    :param s3_uploader: S3Uploader object
    :param env: comma separated list of environment variables
    :param env_blacklist: comma separated list of blacklisted environment variables
    :param job_folder: S3 bucket subfolder
    :param env_file: environment file name
    :param timeout: S3 expiration time in seconds
    :param log: log
    """
    key_value_list = _get_env_key_value_list(env, log, env_blacklist)
    try:
        # copy env to temporary file
        with tempfile.NamedTemporaryFile() as dst:
            dst.write("\n".join(key_value_list) + "\n")
            s3_uploader.put_file(dst.name, job_folder + env_file, timeout)
    except Exception as e:
        fail("Error creating environment file. Failed with exception: %s" % e)


def _compose_bash_command(args, s3_bucket, region, job_folder, job_script, env_file):
    """
    Define bash command to execute.

    :param args: input arguments
    :param s3_bucket: S3 bucket
    :param region: AWS region
    :param job_folder: S3 bucket subfolder
    :param job_script: job script file
    :param env_file: environment file
    :return: composed bash command
    """
    command_args = shell_join(args.arguments)
    # download awscli, if required.
    bash_command = (
        "curl -O https://bootstrap.pypa.io/get-pip.py >/dev/null 2>&1 && "
        "python get-pip.py --user >/dev/null 2>&1 && "
        "export PATH=~/.local/bin:$PATH >/dev/null 2>&1 && "
        "pip install awscli --upgrade --user >/dev/null 2>&1; "
        if args.awscli
        else ""
    )
    # download all job files to a tmp subfolder
    bash_command += (
        "mkdir -p /tmp/{FOLDER} && "
        "aws s3 --region {REGION} sync s3://{BUCKET}/{FOLDER} /tmp/{FOLDER}; ".format(
            REGION=region, BUCKET=s3_bucket, FOLDER=job_folder
        )
    )
    if env_file:
        # source the environment file
        bash_command += "source /tmp/{FOLDER}{ENV_FILE}; ".format(FOLDER=job_folder, ENV_FILE=env_file)
    # execute the job script + arguments
    bash_command += "chmod +x /tmp/{FOLDER}{SCRIPT} && /tmp/{FOLDER}{SCRIPT} {ARGS}".format(
        FOLDER=job_folder, SCRIPT=job_script, ARGS=command_args
    )
    return bash_command


def _get_env_key_value_list(env_vars, log, env_blacklist_vars=None):
    """
    Get key-value environment variables list by excluding blacklisted and internal variables.

    :param env_vars: list of variables to get from the environment and add to the list
    or use 'all' to add all the list except the blacklisted ones
    :param env_blacklist_vars: list of variable names to exclude when 'all' is passed as env_vars parameter
    """
    environment_blacklist = ["HOME", "LD_LIBRARY_PATH", "PATH", "PWD", "TERM", "TERMCAP", "USER", "VCPUS"]

    blacklisted_vars = (
        [var.strip() for var in env_blacklist_vars.split(",")] if env_blacklist_vars else environment_blacklist
    )

    key_value_list = []
    for var in env_vars.split(","):
        var_name = var.strip()

        if var_name == "all":
            # export all the env variables except the blacklisted and the internal ones
            log.info("Environment blacklist is (%s)", blacklisted_vars)
            for env_var in os.environ:
                if env_var not in blacklisted_vars:
                    _add_env_var_to_list(key_value_list, env_var, log)
        elif var_name in os.environ:
            # export variables explicitly specified by the user
            _add_env_var_to_list(key_value_list, var_name, log)
        else:
            log.warn("Environment variable (%s) does not exist." % var_name)

    return key_value_list


def _add_env_var_to_list(key_value_list, var_name, log):
    """
    Get key-value environment variable and add to the given list.

    Skip internal variables and functions.

    :param key_value_list: list to update
    :param var_name: var name
    :param log: log file
    """
    var = var_name.upper()
    # exclude reserved variables and functions
    if (
        not var.startswith("PCLUSTER_")  # reserved AWS ParallelCluster variables
        and not var.startswith("AWS_BATCH_")  # reserved AWS Batch variables
        and not var.startswith("LESS_TERMCAP_")  # terminal variables
        and "()" not in var  # functions
    ):
        var_value = os.environ[var_name]
        key_value_list.append("export %s=%s;" % (var_name, pipes.quote(var_value)))
        log.info("Exporting environment variable: (%s=%s)." % (var_name, var_value))
    else:
        log.warn("Excluded variable: (%s)." % var_name)


def _get_depends_on(args):
    """
    Get depends_on list by parsing input parameters.

    :param args: input parameters
    :return: depends_on list
    """
    depends_on = []
    if args.depends_on:
        dependencies = {}
        try:
            for dependency in args.depends_on.split(","):
                dep = dependency.split("=")
                dependencies[dep[0]] = dep[1]
        except IndexError:
            fail("Parameters validation error: please double check --depends-on parameter syntax.")
        depends_on.append(dependencies)
    return depends_on


class AWSBsubCommand(object):
    """awsbsub command."""

    def __init__(self, log, boto3_factory):
        """
        Constructor.

        :param log: log
        :param boto3_factory: an initialized Boto3ClientFactory object
        """
        self.log = log
        self.batch_client = boto3_factory.get_client("batch")

    def run(  # noqa: C901 FIXME
        self,
        job_definition,
        job_name,
        job_queue,
        command,
        nodes=None,
        vcpus=None,
        memory=None,
        array_size=None,
        retry_attempts=1,
        timeout=None,
        dependencies=None,
        master_ip=None,
    ):
        """Submit the job."""
        try:
            # array properties
            array_properties = {}
            if array_size:
                array_properties.update(size=array_size)

            retry_strategy = {"attempts": retry_attempts}

            depends_on = dependencies if dependencies else []

            # populate container overrides
            container_overrides = {"command": command}
            if vcpus:
                container_overrides.update(vcpus=vcpus)
            if memory:
                container_overrides.update(memory=memory)
            # populate environment variables
            environment = []
            if master_ip:
                environment.append({"name": "MASTER_IP", "value": master_ip})
            container_overrides.update(environment=environment)

            # common submission arguments
            submission_args = {
                "jobName": job_name,
                "jobQueue": job_queue,
                "dependsOn": depends_on,
                "retryStrategy": retry_strategy,
            }

            if nodes:
                # Multi Node parallel submission
                job_definition_version = self.__get_mnp_job_definition_version(
                    base_job_definition_arn=job_definition, nodes=nodes
                )
                submission_args.update({"jobDefinition": job_definition_version})

                target_nodes = "0:%d" % (nodes - 1)
                # populate node overrides
                node_overrides = {
                    "nodePropertyOverrides": [{"targetNodes": target_nodes, "containerOverrides": container_overrides}]
                }
                submission_args.update({"nodeOverrides": node_overrides})
                if timeout:
                    submission_args.update({"timeout": {"attemptDurationSeconds": timeout}})
            else:
                # Standard submission
                submission_args.update({"jobDefinition": job_definition})
                submission_args.update({"containerOverrides": container_overrides})
                submission_args.update({"arrayProperties": array_properties})
                if timeout:
                    submission_args.update({"timeout": {"attemptDurationSeconds": timeout}})

            self.log.debug("Job submission args: %s" % submission_args)
            response = self.batch_client.submit_job(**submission_args)
            print("Job %s (%s) has been submitted." % (response["jobId"], response["jobName"]))
        except Exception as e:
            fail("Error submitting job to AWS Batch. Failed with exception: %s" % e)

    def __get_mnp_job_definition_version(self, base_job_definition_arn, nodes):
        """
        Get (and create if required) job definition version to use for the submission.

        :return: job definition arn
        """
        # Check if there is already a job definition for the given number of nodes
        job_definition_found = self.__search_for_job_definition(base_job_definition_arn, nodes)
        if job_definition_found:
            job_definition_arn = job_definition_found["jobDefinitionArn"]
            self.log.info("Found existing Job definition (%s) with (%i) nodes" % (job_definition_arn, nodes))
        else:
            self.log.info("Creating new Job definition with (%i) nodes" % nodes)
            # create a new job definition revision
            job_definition_arn = self.__register_new_job_definition(base_job_definition_arn, nodes)

        self.log.info("Job definition to use is (%s)" % job_definition_arn)
        return job_definition_arn

    def __search_for_job_definition(self, base_job_definition, nodes):
        """
        Search for existing job definition with the same name of the base_job_definition and the same number of nodes.

        :param base_job_definition: job definition arn
        :param nodes: number of nodes
        :return: the found jobDefinition object or None
        """
        job_definition_found = None
        base_job_definition_name = get_job_definition_name_by_arn(base_job_definition)
        try:
            next_token = ""
            while next_token is not None:
                response = self.batch_client.describe_job_definitions(
                    jobDefinitionName=base_job_definition_name, status="ACTIVE", nextToken=next_token
                )
                for job_definition in response["jobDefinitions"]:
                    if job_definition["nodeProperties"]["numNodes"] == nodes:
                        job_definition_found = job_definition
                        break
                next_token = response.get("nextToken")
        except Exception as e:
            fail("Error listing job definition. Failed with exception: %s" % e)

        return job_definition_found

    def __register_new_job_definition(self, base_job_definition_arn, nodes):
        """
        Register a new job definition.

        It uses the base_job_definition_arn as starting point for the nodeRangeProperties.

        :param base_job_definition_arn: job definition arn to use as starting point
        :param nodes: nuber of nodes to set in the job definition
        :return: the ARN of the created job definition
        """
        try:
            # get base job definition and reuse its nodeRangeProperties
            response = self.batch_client.describe_job_definitions(
                jobDefinitions=[base_job_definition_arn], status="ACTIVE"
            )
            job_definition = response["jobDefinitions"][0]

            # create new job definition
            response = self.batch_client.register_job_definition(
                jobDefinitionName=job_definition["jobDefinitionName"],
                type="multinode",
                nodeProperties={
                    "numNodes": nodes,
                    "mainNode": 0,
                    "nodeRangeProperties": [
                        {
                            "targetNodes": "0:%d" % (nodes - 1),
                            "container": job_definition["nodeProperties"]["nodeRangeProperties"][0]["container"],
                        }
                    ],
                },
            )
            job_definition_arn = response["jobDefinitionArn"]
        except Exception as e:
            fail("Error listing job definition. Failed with exception: %s" % e)

        return job_definition_arn


def main():
    """Command entrypoint."""
    try:
        # parse input parameters and config file
        args = _get_parser().parse_args()
        _validate_parameters(args)
        log = config_logger(args.log_level)
        log.info("Input parameters: %s" % args)
        config = AWSBatchCliConfig(log=log, cluster=args.cluster)
        boto3_factory = Boto3ClientFactory(
            region=config.region,
            proxy=config.proxy,
            aws_access_key_id=config.aws_access_key_id,
            aws_secret_access_key=config.aws_secret_access_key,
        )

        # define job name
        if args.job_name:
            job_name = args.job_name
        else:
            # set a default job name if not specified
            if not sys.stdin.isatty():
                # stdin
                job_name = "STDIN"
            else:
                # normalize name
                job_name = re.sub(r"\W+", "_", os.path.basename(args.command))
            log.info("Job name not specified, setting it to (%s)" % job_name)

        # upload script, if needed, and get related command
        command = _upload_and_get_command(boto3_factory, args, job_name, config, log)
        # parse and validate depends_on parameter
        depends_on = _get_depends_on(args)

        # select submission (standard vs MNP)
        if args.nodes:
            if not hasattr(config, "job_definition_mnp"):
                fail("Current cluster does not support MNP jobs submission")
            job_definition = config.job_definition_mnp
        else:
            job_definition = config.job_definition

        AWSBsubCommand(log, boto3_factory).run(
            job_definition=job_definition,
            job_name=job_name,
            job_queue=config.job_queue,
            command=command,
            nodes=args.nodes,
            vcpus=args.vcpus,
            memory=args.memory,
            array_size=args.array_size,
            dependencies=depends_on,
            retry_attempts=args.retry_attempts,
            timeout=args.timeout,
            master_ip=config.master_ip,
        )
    except KeyboardInterrupt:
        print("Exiting...")
        sys.exit(0)
    except Exception as e:
        fail("Unexpected error. Command failed with exception: %s" % e)


if __name__ == "__main__":
    main()
