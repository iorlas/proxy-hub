FROM alpine:3.20 AS build
RUN apk add --no-cache gcc musl-dev git make
RUN git clone https://github.com/rofl0r/microsocks.git /src && cd /src && make

FROM alpine:3.20
COPY --from=build /src/microsocks /usr/local/bin/microsocks
EXPOSE 1080
ENTRYPOINT ["microsocks"]
CMD ["-i", "0.0.0.0", "-p", "1080"]
