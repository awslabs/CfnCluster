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
import logging
import os
import re
from shutil import copyfile

import pytest
from assertpy import assert_that
from jinja2 import Environment, FileSystemLoader
from remote_command_executor import RemoteCommandExecutor
from utils import get_compute_nodes_instance_ids

from tests.common.assertions import assert_no_errors_in_logs
from tests.common.mpi_common import _test_mpi
from tests.common.schedulers_common import get_scheduler_commands
from tests.common.utils import fetch_instance_slots


@pytest.mark.regions(["us-east-1"])
@pytest.mark.instances(["c5n.18xlarge"])
@pytest.mark.oss(["alinux2"])
@pytest.mark.schedulers(["slurm"])
@pytest.mark.usefixtures("os")
def test_hit_efa(
    region,
    scheduler,
    instance,
    pcluster_config_reader,
    clusters_factory,
    test_datadir,
    architecture,
    network_interfaces_count,
):
    """
    Test all EFA Features.

    Grouped all tests in a single function so that cluster can be reused for all of them.
    """
    max_queue_size = 4
    slots_per_instance = fetch_instance_slots(region, instance)
    no_efa_instance = "t3.micro" if architecture == "x86_64" else "t4g.micro"
    cluster_config = pcluster_config_reader(max_queue_size=max_queue_size, no_efa_instance=no_efa_instance)
    cluster = clusters_factory(cluster_config)
    remote_command_executor = RemoteCommandExecutor(cluster)
    scheduler_commands = get_scheduler_commands(scheduler, remote_command_executor)

    _test_efa_installation(scheduler_commands, remote_command_executor, efa_installed=True, partition="efa-enabled")
    _test_efa_installation(
        scheduler_commands, remote_command_executor, efa_installed=True, partition="efa-enabled-by-default"
    )
    _test_efa_installation(scheduler_commands, remote_command_executor, efa_installed=False, partition="efa-disabled")
    _test_efa_installation(
        scheduler_commands, remote_command_executor, efa_installed=False, partition="efa-disabled-by-default"
    )
    _test_mpi(remote_command_executor, slots_per_instance, scheduler, partition="efa-enabled")
    logging.info("Running on Instances: {0}".format(get_compute_nodes_instance_ids(cluster.cfn_name, region)))

    benchmark_failures = []
    mpi_versions = ["openmpi"]
    if architecture == "x86_64":
        mpi_versions.append("intelmpi")

    for efa_queue_name in ["efa-enabled", "efa-enabled-by-default"]:
        # OSU benchmarks are time expensive.
        # Run a subset of benchmarks in efa-enabled-by-default and all of them in efa-enabled.
        for mpi_version in mpi_versions:
            benchmark_failures.extend(
                _test_osu_benchmarks_pt2pt(
                    mpi_version,
                    remote_command_executor,
                    scheduler_commands,
                    test_datadir,
                    slots_per_instance,
                    benchmarks=["osu_latency"] if efa_queue_name == "efa-enabled-by-default" else None,
                    partition=efa_queue_name,
                )
            )
        benchmark_failures.extend(
            _test_osu_benchmarks_collective(
                mpi_version,
                remote_command_executor,
                scheduler_commands,
                test_datadir,
                slots_per_instance,
                benchmarks=["osu_allgather", "osu_alltoall"] if efa_queue_name == "efa-enabled-by-default" else None,
                partition=efa_queue_name,
            )
        )
        assert_that(benchmark_failures, description="Some OSU benchmarks are failing").is_empty()
        if network_interfaces_count > 1:
            _test_osu_benchmarks_multiple_bandwidth(
                remote_command_executor, scheduler_commands, test_datadir, slots_per_instance, partition=efa_queue_name
            )
        _test_shm_transfer_is_enabled(scheduler_commands, remote_command_executor, partition=efa_queue_name)

    assert_no_errors_in_logs(remote_command_executor, scheduler)


def _test_efa_installation(scheduler_commands, remote_command_executor, efa_installed=True, partition=None):
    # Output contains:
    # 00:06.0 Ethernet controller: Amazon.com, Inc. Device efa0
    logging.info("Testing EFA installed")
    if partition:
        result = scheduler_commands.submit_command("lspci -n > /shared/lspci.out", partition=partition)
    else:
        result = scheduler_commands.submit_command("lspci -n > /shared/lspci.out")
    job_id = scheduler_commands.assert_job_submitted(result.stdout)
    scheduler_commands.wait_job_completed(job_id)
    scheduler_commands.assert_job_succeeded(job_id)

    # Check if EFA interface is on compute node
    result = remote_command_executor.run_remote_command("cat /shared/lspci.out")
    if efa_installed:
        assert_that(result.stdout).contains("1d0f:efa")
    else:
        assert_that(result.stdout).does_not_contain("1d0f:efa")

    # Check EFA interface not present on head node
    result = remote_command_executor.run_remote_command("lspci -n")
    assert_that(result.stdout).does_not_contain("1d0f:efa")


def _test_osu_benchmarks_pt2pt(
    mpi_version,
    remote_command_executor,
    scheduler_commands,
    test_datadir,
    slots_per_instance,
    benchmarks=None,
    partition=None,
):
    # OSU pt2pt benchmarks cannot be executed with more than 2 MPI ranks.
    # Run them it in 2 instances with 1 proc per instance, defined by map-by parameter.
    num_of_instances = 2
    # Accept a max number of 4 failures on a total of 23-24 packet size tests.
    accepted_number_of_failures = 4

    failed_benchmarks = []
    testing_benchmarks = benchmarks or ["osu_latency", "osu_bibw"]
    for benchmark_name in testing_benchmarks:
        output = run_osu_benchmarks(
            mpi_version,
            "pt2pt",
            benchmark_name,
            partition,
            remote_command_executor,
            scheduler_commands,
            num_of_instances,
            slots_per_instance,
            test_datadir,
        )
        failures = _check_osu_benchmarks_results(
            test_datadir, mpi_version, benchmark_name, output, accepted_tolerance=0.2
        )
        if failures > accepted_number_of_failures:
            failed_benchmarks.append(f"{mpi_version}-{benchmark_name}")

    return failed_benchmarks


def _test_osu_benchmarks_collective(
    mpi_version,
    remote_command_executor,
    scheduler_commands,
    test_datadir,
    slots_per_instance,
    benchmarks=None,
    partition=None,
):
    # OSU collective benchmarks can be executed with any number of instances,
    # 4 instances are enough to see performance differences
    num_of_instances = 4
    # Accept a max number of 3 failures on a total of 19-21 packet size tests.
    accepted_number_of_failures = 3

    failed_benchmarks = []
    testing_benchmarks = benchmarks or ["osu_allgather", "osu_bcast", "osu_allreduce", "osu_alltoall"]
    for benchmark_name in testing_benchmarks:
        output = run_osu_benchmarks(
            mpi_version,
            "collective",
            benchmark_name,
            partition,
            remote_command_executor,
            scheduler_commands,
            num_of_instances,
            slots_per_instance,
            test_datadir,
        )
        failures = _check_osu_benchmarks_results(test_datadir, mpi_version, benchmark_name, output)
        if failures > accepted_number_of_failures:
            failed_benchmarks.append(f"{mpi_version}-{benchmark_name}")

    return failed_benchmarks


def _test_osu_benchmarks_multiple_bandwidth(
    remote_command_executor, scheduler_commands, test_datadir, slots_per_instance, partition=None
):
    num_of_instances = 2
    run_osu_benchmarks(
        "openmpi",
        "mbw_mr",
        "mbw_mr",
        partition,
        remote_command_executor,
        scheduler_commands,
        num_of_instances,
        slots_per_instance,
        test_datadir,
    )
    max_bandwidth = remote_command_executor.run_remote_command(
        "cat /shared/osu.out | tail -n +4 | awk '{print $2}' | sort -n | tail -n 1"
    ).stdout

    # Expected bandwidth with 4 NICS:
    # OMPI 4.1.0: ~330Gbps = 41250MB/s
    # OMPI 4.0.5: ~95Gbps = 11875MB/s
    assert_that(float(max_bandwidth)).is_greater_than(41000)


def run_osu_benchmarks(
    mpi_version,
    benchmark_group,
    benchmark_name,
    partition,
    remote_command_executor,
    scheduler_commands,
    num_of_instances,
    slots_per_instance,
    test_datadir,
):
    osu_benchmark_version = "5.7.1"
    logging.info(f"Running OSU benchmark {osu_benchmark_version}: {benchmark_name} for {mpi_version}")

    # Init OSU benchmarks
    init_script = _render_jinja_template(
        template_file_path=test_datadir / "init_osu_benchmarks.sh", osu_benchmark_version=osu_benchmark_version
    )
    remote_command_executor.run_remote_script(
        str(init_script),
        args=[mpi_version],
        hide=True,
        additional_files=[
            str(test_datadir / "osu_benchmarks" / f"osu-micro-benchmarks-{osu_benchmark_version}.tgz"),
            str(test_datadir / "osu_benchmarks" / "config.guess"),
            str(test_datadir / "osu_benchmarks" / "config.sub"),
        ],
    )

    # Prepare submission script and pass to the scheduler for the job submission
    copyfile(
        test_datadir / f"osu_{benchmark_group}_submit_{mpi_version}.sh",
        test_datadir / f"osu_{benchmark_group}_submit_{mpi_version}_{benchmark_name}.sh",
    )
    slots = num_of_instances * slots_per_instance
    submission_script = _render_jinja_template(
        template_file_path=test_datadir / f"osu_{benchmark_group}_submit_{mpi_version}_{benchmark_name}.sh",
        benchmark_name=benchmark_name,
        osu_benchmark_version=osu_benchmark_version,
        num_of_processes=slots,
    )
    if partition:
        result = scheduler_commands.submit_script(str(submission_script), slots=slots, partition=partition)
    else:
        result = scheduler_commands.submit_script(str(submission_script), slots=slots)
    job_id = scheduler_commands.assert_job_submitted(result.stdout)
    scheduler_commands.wait_job_completed(job_id)
    scheduler_commands.assert_job_succeeded(job_id)

    output = remote_command_executor.run_remote_command(f"cat /shared/{benchmark_name}.out").stdout
    return output


def _check_osu_benchmarks_results(test_datadir, mpi_version, benchmark_name, output, accepted_tolerance=0.1):
    # Check avg latency for all packet sizes, with a tolerance of 10% for collective tests and 20% for pt2pt tests.
    failures = 0
    for packet_size, latency in re.findall(r"(\d+)\s+(\d+)\.", output):
        with open(str(test_datadir / "osu_benchmarks_results" / mpi_version / benchmark_name)) as osu_results:
            previous_result = re.search(rf"{packet_size}\s+(\d+)\.", osu_results.read()).group(1)
            expected_latency = int(previous_result) + float(previous_result) * accepted_tolerance

            message = (
                f"{mpi_version} - {benchmark_name} - packet size {packet_size}: "
                f"expected: {expected_latency}, current: {latency}"
            )
            if int(latency) >= expected_latency:
                failures = failures + 1
                logging.error(message)
            else:
                logging.info(message)

    return failures


def _test_shm_transfer_is_enabled(scheduler_commands, remote_command_executor, partition=None):
    logging.info("Testing SHM Transfer is enabled")
    if partition:
        result = scheduler_commands.submit_command("fi_info -p efa 2>&1 > /shared/fi_info.out", partition=partition)
    else:
        result = scheduler_commands.submit_command("fi_info -p efa 2>&1 > /shared/fi_info.out")
    job_id = scheduler_commands.assert_job_submitted(result.stdout)
    scheduler_commands.wait_job_completed(job_id)
    scheduler_commands.assert_job_succeeded(job_id)
    result = remote_command_executor.run_remote_command("cat /shared/fi_info.out")
    assert_that(result.stdout).does_not_contain("SHM transfer will be disabled because of ptrace protection")


def _render_jinja_template(template_file_path, **kwargs):
    file_loader = FileSystemLoader(str(os.path.dirname(template_file_path)))
    env = Environment(loader=file_loader)
    rendered_template = env.get_template(os.path.basename(template_file_path)).render(**kwargs)
    with open(template_file_path, "w") as f:
        f.write(rendered_template)
    return template_file_path
