# Test Dockerfile for Promtail static

This folder includes a battery of `Dockerfile`s to validate static builds of promtail.
The images are very simple: they take a base, add promtail to it, and set the entrypoint to running `promtail --version`.
If promtail is dynamically compiled and incompatible with the base image (e.g., wrong libc), running the container image will fail with:

```sh
michele@boombox:/tmp/loki$ docker run promtail-alpine-dynamic
standard_init_linux.go:228: exec user process caused: no such file or directory
```

If promtail can run on top of the provided base, the output will look like the following:

```sh
michele@boombox:/tmp/loki$ docker run promtail-alpine
promtail, version  (branch: , revision: )
  build user:       
  build date:       
  go version:       go1.17.8
  platform:         linux/amd64
```

## How to add more test base images

1. Add a `Dockerfile.<base>` in this folder
2. Add `<base>` to the matrix of the `test` job in the [Build promtail](.github/workflows/build-promtail-release.yaml) GitHub workflow
