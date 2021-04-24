#! /usr/bin/env bash

flatpak-builder --repo=hello-repo --force-clean build-dir org.freedesktop.Sdk.Extension.Hello.yaml
flatpak --user remote-add --if-not-exists --no-gpg-verify hello-repo hello-repo
rm -rf build-dir .flatpak-builder
