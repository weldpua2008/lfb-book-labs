FROM eclipse-temurin:21.0.13_9-jdk-noble@sha256:06c1f157dacf6b68198bd9a4186dd4c34ef24e65d7bbbe2a0cf8e62571ad38c9
WORKDIR /opt/havelblick
COPY lib/ lib/
COPY src/ src/
RUN mkdir classes && find src -name '*.java' | LC_ALL=C sort > sources.txt && javac --release 21 -encoding UTF-8 -d classes @sources.txt && jar --create --file havelblick.jar --date=2026-11-18T00:00:00Z -C classes .
USER 10001:10001
ENTRYPOINT ["java","-Xmx128m","-cp","havelblick.jar:lib/*"]
CMD ["havelblick.Main","app"]
