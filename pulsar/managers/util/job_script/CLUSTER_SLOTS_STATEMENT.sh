export GALAXY_SLOTS_CONFIGURED="1"
if [ -n "$SLURM_CPUS_ON_NODE" ]; then
    # This should be valid on SLURM except in the case that srun is used to
    # submit additional job steps under an existing allocation, which we do not
    # currently do.
    GALAXY_SLOTS="$SLURM_CPUS_ON_NODE"
elif [ -n "$SLURM_NTASKS" ] || [ -n "$SLURM_CPUS_PER_TASK" ]; then
    # $SLURM_CPUS_ON_NODE should be set correctly on SLURM (even on old
    # installations), but keep the $SLURM_NTASKS logic as a backup since this
    # was the previous method under SLURM.
    #
    # Multiply these values since SLURM_NTASKS is total tasks over all nodes.
    # GALAXY_SLOTS maps to CPUS on a single node and shouldn't be used for
    # multi-node requests.
    GALAXY_SLOTS=`expr "${SLURM_NTASKS:-1}" \* "${SLURM_CPUS_PER_TASK:-1}"`
elif [ -n "$NSLOTS" ]; then
    GALAXY_SLOTS="$NSLOTS"
elif [ -n "$NCPUS" ]; then
    GALAXY_SLOTS="$NCPUS"
elif [ -n "$PBS_NCPUS" ]; then
    GALAXY_SLOTS="$PBS_NCPUS"
elif [ -f "$PBS_NODEFILE" ]; then
    GALAXY_SLOTS=`wc -l < $PBS_NODEFILE`
elif [ -n "$LSB_DJOB_NUMPROC" ]; then
    GALAXY_SLOTS="$LSB_DJOB_NUMPROC"
elif [ -n "$GALAXY_SLOTS" ]; then
    # kubernetes runner injects GALAXY_SLOTS into environment
    GALAXY_SLOTS=$GALAXY_SLOTS
elif [ -n "$ROOT_MAX_THREADS" ]; then
    # HTCondor sets a couple of environment variables read by various
    # frameworks to control the number of threads they are allowed to use. A
    # list can be found in the HTCondor docs (the list itself is configurable,
    # as it is an HTCondor configuration macro).
    #
    # https://htcondor.readthedocs.io/en/24.0/admin-manual/
    # configuration-macros.html#STARTER_NUM_THREADS_ENV_VARS
    #
    # Any of these variables can be used to set GALAXY_SLOTS. Set it using the
    # variable ROOT_MAX_THREADS (designed to control the ROOT data analysis
    # framework from CERN).
    GALAXY_SLOTS="$ROOT_MAX_THREADS"
else
    GALAXY_SLOTS="1"
    unset GALAXY_SLOTS_CONFIGURED
fi
export GALAXY_SLOTS
