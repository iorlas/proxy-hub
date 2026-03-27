FROM alpine:3.20 AS build
# hadolint ignore=DL3018
RUN apk add --no-cache gcc musl-dev git make
WORKDIR /src
RUN git clone https://github.com/rofl0r/microsocks.git . && make

FROM alpine:3.20
RUN adduser -D -s /sbin/nologin microsocks
COPY --from=build /src/microsocks /usr/local/bin/microsocks
HEALTHCHECK CMD /usr/local/bin/microsocks --help || exit 1
USER microsocks
EXPOSE 1080
ENTRYPOINT ["microsocks"]
CMD ["-i", "0.0.0.0", "-p", "1080"]
