# Operator-built tool image. Resolve BASE to an immutable digest before building.
ARG BASE
FROM ${BASE}
RUN apt-get update && apt-get install -y --no-install-recommends python3 xvfb libx11-6 libxcursor1 libxi6 libxinerama1 libxrandr2 libgl1 libfontconfig1 libasound2t64 && rm -rf /var/lib/apt/lists/*
COPY godot /usr/local/bin/godot
COPY runner.py compile.gd probe.gd package.gd smoke.gd driver.gd title_runner.py title_package.gd smith_recipe.json /recipe/
RUN chmod 0555 /usr/local/bin/godot && chmod -R a+rX /recipe
USER 65534:65534
ENV HOME=/tmp XDG_CACHE_HOME=/tmp XDG_CONFIG_HOME=/tmp PYTHONDONTWRITEBYTECODE=1
WORKDIR /work
ENTRYPOINT ["/usr/bin/python3", "-I", "/recipe/runner.py"]
