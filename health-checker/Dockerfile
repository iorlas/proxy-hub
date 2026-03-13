FROM alpine:3.21

RUN apk add --no-cache redis netcat-openbsd

COPY health-check.sh /usr/local/bin/health-check.sh
RUN chmod +x /usr/local/bin/health-check.sh

CMD ["/usr/local/bin/health-check.sh"]
