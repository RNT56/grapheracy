FROM node:24-slim

RUN useradd --create-home --shell /usr/sbin/nologin graphview
WORKDIR /app
USER graphview

CMD ["node", "-e", "console.log('Graphview web image placeholder for Phase 2')"]
