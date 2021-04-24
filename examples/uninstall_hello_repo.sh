#! /usr/bin/env bash

flatpak --user uninstall -y org.freedesktop.Sdk.Extension.Hello/x86_64/20.08 2>/dev/null
flatpak --user remote-delete hello-repo 2>/dev/null
rm -rf hello-repo build-dir .flatpak-builder
