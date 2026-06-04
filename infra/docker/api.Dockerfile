FROM python:3.14-slim

RUN useradd --create-home --shell /usr/sbin/nologin graphview
WORKDIR /app
USER graphview

CMD ["python", "-c", "print('Graphview API image placeholder for Phase 2')"]
