FROM dxflrs/garage:v2.3.0@sha256:866bd13ed2038ba7e7190e840482bc27234c4afaf77be8cfa439ae088c1e4690 AS garage
FROM alpine@sha256:28bd5fe8b56d1bd048e5babf5b10710ebe0bae67db86916198a6eec434943f8b
COPY --from=garage /garage /garage
ENTRYPOINT ["/bin/sh", "-c", "set -a; . /run/config/file.env; exec /garage -c /run/config/garage.toml server --single-node --default-bucket"]
