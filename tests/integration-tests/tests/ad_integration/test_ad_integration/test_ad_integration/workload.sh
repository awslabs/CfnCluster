#!/bin/bash
set -ex

for fspath in shared; do
    # srun has to be used for whoami because slurm_nss plugin only send user information through srun
    date '+%Y%m%d%H%M%S' > "/$fspath/$(srun whoami)"
done
