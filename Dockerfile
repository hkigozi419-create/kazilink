FROM python:3.12-slim
WORKDIR /app
COPY . /app
ENV KAZILINK_HOST=0.0.0.0
ENV KAZILINK_PORT=8080
EXPOSE 8080
CMD ["python", "kazilink_server.py"]
