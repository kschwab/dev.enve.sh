#!/bin/sh -i

export ENV=/usr/lib/sdk/enve/etc/enve_bashrc
export BASH_ENV=$ENV
source $ENV
eval $@