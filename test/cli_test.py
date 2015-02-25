from pulsar.managers.util.cli import factory


def test_torque_cli():
    job_params = dict(
        plugin="Torque",
        Priority="4",
    )
    job = __build_job_interface(job_params)

    command = job.submit("/tmp/path/test.sh")
    assert command == "qsub /tmp/path/test.sh"

    command = job.delete("5")
    assert command == "qdel 5"

    command = job.get_status()
    assert command == "qstat -x"

    job_script_kwargs = job.job_script_kwargs("/tmp/1/o", "/tmp/1/e", "my_job")
    headers = job_script_kwargs["headers"]
    # Verify priority from job params pass through
    assert "#PBS -p 4" in headers

    # Verify it just skips invalid status...
    assert job.parse_status("Warning: Network Proble.", ["24", "25"]) is None

    output = "<Data><Job><Job_Id>24</Job_Id><job_state>Q</job_state></Job>"
    output += "<Job><Job_Id>25</Job_Id><job_state>E</job_state></Job>"
    output += "<Job><Job_Id>26</Job_Id><job_state>E</job_state></Job></Data>\n"
    status_dict = job.parse_status(output, ["24", "25"])
    assert status_dict["24"] == "queued"
    assert status_dict["25"] == "running"
    assert "26" not in status_dict


def test_slurm_cli():
    job_params = dict(
        plugin="Slurm",
        ncpus=5
    )
    job = __build_job_interface(job_params)

    command = job.submit("/tmp/path/test.sh")
    assert command == "sbatch /tmp/path/test.sh"

    command = job.get_status()
    assert command == '''squeue -a -o '%A %t\''''

    command = job.get_single_status("4")
    assert command == '''squeue -a -o '%A %t' -j 4'''

    job_script_kwargs = job.job_script_kwargs("/tmp/1/o", "/tmp/1/e", "my_job")
    headers = job_script_kwargs["headers"]
    assert "#SBATCH -o /tmp/1/o" in headers
    assert "#SBATCH -e /tmp/1/e" in headers
    assert "#SBATCH -J my_job" in headers
    assert "#SBATCH -c 5" in headers

    output = """JOBID ST\n24 PD\n25 R\n26 F\n"""
    status_dict = job.parse_status(output, ["24", "25"])

    assert status_dict["24"] == "queued"
    assert status_dict["25"] == "running"
    assert "26" not in status_dict

    status = job.parse_single_status("slurm_load_jobs error: Invalid job id specified", "34")
    assert status == "complete"

    status = job.parse_single_status("JOBID ST\n26 F\n", "26")
    assert status == "failed"


def test_slurm_torque():
    job_params = dict(
        plugin="SlurmTorque",
    )
    job = __build_job_interface(job_params)

    command = job.submit("/tmp/path/test.sh")
    assert command == "qsub /tmp/path/test.sh"

    command = job.get_status()
    assert command == "qstat"

    output = """Job ID              Jobname          Username        Time     S Queue          \n"""
    output += """24                  script.sh        john            00:00:00 R debug          \n"""
    output += """27                  script2.sh        mary            00:00:00 R debug          \n"""
    stats = job.parse_status(output, ["24", "25"])
    assert stats.get("24", None) == "running", stats
    assert "25" not in stats


def __build_job_interface(job_params):
    cli_interface = factory.build_cli_interface()
    _, job = cli_interface.get_plugins({}, job_params)
    return job
