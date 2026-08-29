"""The canned result for ``demo_mode="fixture"``.

`fixture` has to hold with the network unplugged, which rules out a hosted placeholder: an
``https`` URL that 404s offline would look like a broken generation rather than a fixture. The
image is therefore an inline SVG data URI — it renders in an ``<img>`` with no socket opened,
and it is visibly a stand-in rather than something passed off as generated art.
"""

from __future__ import annotations

import base64

_FIXTURE_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 768 768">'
    '<rect width="768" height="768" fill="#17255f"/>'
    '<circle cx="566" cy="180" r="86" fill="#f5f0d6"/>'
    '<path d="M0 470c150-52 268 44 392-6s224 12 376-52v356H0Z" fill="#3159d7"/>'
    '<path d="M0 566c176-46 322 34 470-14 96-31 178-24 298-58v274H0Z" fill="#779be7"/>'
    '<path d="M232 268h224v232H232z" fill="#0c1338"/>'
    '<path d="m204 268 140-96 140 96Z" fill="#d2d9ec"/>'
    '<rect x="272" y="360" width="52" height="140" fill="#f2c35e"/>'
    "</svg>"
)

#: Base64 rather than percent-encoding: it survives being pasted, logged and round-tripped
#: through JSON without a quoting argument.
FIXTURE_IMAGE_URL = (
    "data:image/svg+xml;base64,"
    + base64.b64encode(_FIXTURE_SVG.encode("utf-8")).decode("ascii")
)


def fixture_model(model: str) -> str:
    """Name the model that *would* have run, and say plainly that it did not.

    Reporting the bare model id here would be a small lie in the one field whose job is to say
    what produced the image.
    """
    return f"fixture:{model}"
