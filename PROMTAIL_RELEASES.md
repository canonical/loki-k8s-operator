# Static releases of Promtail binaries

In order to support any container running Linux with the [LogProxyConsumer](lib/charms/loki_k8s/v1/loki_push_api.py), we need builds of `promtail` that are statically linked.

## Why statically linking Promtail?

Static linking is necessary due to the various versions of libc (glibc, muslc), or even the absence of any libc implementation, to be found in containers based on container images other than `ubuntu` and the like.
For example, Alpine-based containers ship muslc.
Distroless-based and "from scratch" containers often have no libc at all.
And the `promtail` builds from [upstream](https://github.com/grafana/loki/releases/) effectively work only on a subset of containers, which is a limitation we cannot afford.

## How we build statically-linked Promtail binaries

The build-and-release process for statically-linked `promtail` binaries is as follows:

1. Every 4 hours, the cron-like [`check-promtail-releases`](.github/workflows/check-promtail-releases.yaml) GitHub workflow compares the latest upstream release of Loki with specific `promtail-*` tags in this repository.
For example, the upstream `v2.4.2` tag pointed at by the upstream release, means that the `check-promtail-releases` workflow checks for a `promtail-v2.4.2` tag in this repository.
2. If an upstream release is found that has no matching `promtail-*` tag, the [`build-promtail-release.yaml`](.github/workflows/build-promtail-release.yaml) is triggered, which:
   1. Statically compile `promtail` for different architectures
   2. Try the binary by building [containers with different base images](promtail-build/static/test) and run then with a `docker run` command
   3. Create a shallow tag of the original Loki codebase (without history) and create the `promtail-*` tag from it.
   4. Create a GitHub release with the promtail binaries, pointing at the `promtail-*` tag
  
