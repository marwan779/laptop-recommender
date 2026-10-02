package main

# Helper Functions & Configuration
allowed_registries := [
    "eclipse-temurin",
    "redhat",
    "amazoncorretto",
    "my-internal-registry.com",
]

is_trusted_image(image) if {
    parts := split(image, "/")
    count(parts) == 1
}

is_trusted_image(image) if {
    parts := split(image, "/")
    count(parts) > 1

    some reg in allowed_registries
    parts[0] == reg
}
# Rule 1: Block secrets in ENV keys
secrets_env := [
    "passwd",
    "password",
    "secret",
    "key",
    "token",
    "apikey",
]

deny contains msg if {
    some i
    input[i].Cmd == "env"

    val := lower(input[i].Value)

    some secret in secrets_env
    contains(val, secret)

    msg := sprintf(
        "Line %d: Potential secret in ENV key: %s",
        [i, input[i].Value],
    )
}
# Rule 2: Trusted base images only
deny contains msg if {
    some i
    input[i].Cmd == "from"

    image := input[i].Value[0]

    not is_trusted_image(image)

    msg := sprintf(
        "Line %d: Base image '%s' is not trusted. Use an allowed registry.",
        [i, image],
    )
}
# Rule 3: No 'latest' tags
deny contains msg if {
    some i
    input[i].Cmd == "from"

    image := input[i].Value[0]
    parts := split(image, ":")

    count(parts) > 1
    lower(parts[1]) == "latest"

    msg := sprintf(
        "Line %d: Do not use 'latest' tag for base images.",
        [i],
    )
}
# Rule 4: Avoid curl / wget in RUN
deny contains msg if {
    some i
    input[i].Cmd == "run"

    val := lower(concat(" ", input[i].Value))

    matches := regex.find_n(
        "(curl|wget)[^ ]*",
        val,
        -1,
    )

    count(matches) > 0

    msg := sprintf(
        "Line %d: Avoid curl/wget in RUN.",
        [i],
    )
}
# Rule 5: No system upgrades in RUN
upgrade_cmds := [
    "apk upgrade",
    "apt-get upgrade",
    "dist-upgrade",
]

deny contains msg if {
    some i
    input[i].Cmd == "run"

    val := lower(concat(" ", input[i].Value))

    some upgrade in upgrade_cmds
    contains(val, upgrade)

    msg := sprintf(
        "Line %d: Do not upgrade system packages in Dockerfile.",
        [i],
    )
}
# Rule 6: Use COPY instead of ADD
deny contains msg if {
    some i
    input[i].Cmd == "add"

    msg := sprintf(
        "Line %d: Use COPY instead of ADD.",
        [i],
    )
}
# Rule 7: Must run as a non-root user
has_user_instruction if {
    some i
    input[i].Cmd == "user"
}

user_is_root if {
    some i
    input[i].Cmd == "user"

    user := lower(input[i].Value[0])
    user == "root"
}

user_is_root if {
    some i
    input[i].Cmd == "user"

    input[i].Value[0] == "0"
}

deny contains msg if {
    not has_user_instruction

    msg := "Dockerfile must use USER to switch from root."
}

deny contains msg if {
    user_is_root

    msg := "Dockerfile must not run as root. Use a non-root USER."
}
# Rule 8: No sudo
deny contains msg if {
    some i
    input[i].Cmd == "run"

    val := lower(concat(" ", input[i].Value))

    contains(val, "sudo")

    msg := sprintf(
        "Line %d: Do not use 'sudo' command.",
        [i],
    )
}

#Rule 9: Must use multi-stage builds
has_copy if {
    some i
    input[i].Cmd == "copy"
}

has_multistage if {
    some i
    input[i].Cmd == "copy"

    some flag in input[i].Flags
    contains(lower(flag), "--from=")
}

deny contains msg if {
    has_copy
    not has_multistage

    msg := "Dockerfile uses COPY but lacks multi-stage build (--from=)."
}
