# TechniView internal Judge0 fork

TechniView owns and maintains this internal image, derived from Judge0 1.13.1.
It is not an official Judge0 image and is not published to a registry. The image
runs Python 3.14.8 submissions and keeps Judge0's submission API, callback
delivery, result reports, and Isolate sandbox. It replaces the language seed
data with one active Python runtime, distilling the multi-language image for
TechniView's Python-only runner. It patches the submission endpoint so callers
do not send a language ID.

## Build and run

The development Compose file builds `internal-judge0-fork:local` from this
directory for both the server and worker services:

```sh
docker compose build server workers
docker compose up -d server workers
```

The integration Compose file builds the same Dockerfile and exercises it with
the TechniView backend:

```sh
make integration
```

Compose builds the internal image locally. This repository does not publish it
to a registry or package it separately. The Dockerfile's first stage supplies the
Judge0 application, Ruby gems, and Isolate files. The final image starts from
Judge0's slim compiler image and installs Python 3.14.8 from the official Python
source archive. The archive checksum is pinned in the Dockerfile.

## Language selection and reporting

`languages/active.rb` defines the only active language. `languages/archived.rb`
is empty, so Judge0 seeds no other language runtimes. The active record has an
internal database key because Judge0 stores that key on submission records.
TechniView's public submission model rejects `language_id`, and its Judge0
client omits that field. The fork fills it from the only active language before
Judge0 creates a submission.

The fork keeps Judge0's normal report fields and callback behavior. The
integration suite sends real Python submissions and checks accepted,
wrong-answer, and runtime-error reports, callback completion, and polling
recovery. Run it after changing the Dockerfile, language seed, or API patch.

## Updating the image

The Dockerfile pins the Judge0 application source image and the slim compiler
image by digest. It also pins the Judge0 version, Python version, and Python
source checksum. Update these together, then build both Compose variants and
run `make integration`. Review the changed Judge0 controller patch against the
new upstream source before accepting an upgrade.

The image currently relies on Debian 10 packages and OpenSSL 1.1.1 inherited
from the pinned Judge0 layers. Debian 10 is out of normal security support. The
image is suitable for local development and integration testing, but needs a
maintained OS base before production deployment.
