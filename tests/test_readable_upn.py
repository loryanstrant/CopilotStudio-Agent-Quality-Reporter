"""Showing an unresolvable creator's sign-in address readably.

Copilot Studio can stamp an agent with the maker's Entra object id run straight
into their address — ``20a43a6b…4cfjustin.bell@contoso.com`` — when that maker's
directory record has since been renamed or deleted. The tenant this came from
has exactly one, a former employee, and the lookup failing on them is expected
and not a bug to chase.

What the app does about it is display-only: the stored value is never rewritten,
and the rule that trims it is timid on purpose. A heuristic that mangles a
legitimately unusual address is worse than an ugly address, so the tests below
are mostly about what it refuses to touch.
"""
from __future__ import annotations

import pytest

from api.metrics import readable_upn

OID = "20a43a6b4ea043858a0efbb9e20ce4cf"
DASHED = "20a43a6b-4ea0-4385-8a0e-fbb9e20ce4cf"


def test_an_object_id_in_front_of_an_address_is_trimmed_off():
    assert (
        readable_upn(f"{OID}justin.bell@contoso.com", resolved=False)
        == "justin.bell@contoso.com"
    )


def test_the_dashed_form_is_trimmed_too():
    assert (
        readable_upn(f"{DASHED}justin.bell@contoso.com", resolved=False)
        == "justin.bell@contoso.com"
    )


def test_a_resolved_creator_is_never_touched():
    """The strongest guard: if Entra answered for this person, their stored
    address is the real one whatever it looks like."""
    mashed = f"{OID}justin.bell@contoso.com"
    assert readable_upn(mashed, resolved=True) == mashed


@pytest.mark.parametrize(
    "upn",
    [
        # Ordinary addresses, long and short.
        "a.mcgregor@contoso.com",
        "stef@contoso.com",
        # A local part that *is* 32 hex characters. Trimming leaves "@contoso
        # .com", which is not an address, so nothing is trimmed.
        f"{OID}@contoso.com",
        # 32 hex characters and nothing else — no address to fall back to.
        OID,
        # A hex-looking prefix of the wrong length is not an object id.
        f"{OID[:31]}justin.bell@contoso.com",
        # Not hex at all.
        f"20a43a6b4ea043858a0efbb9e20ce4cz{OID}@contoso.com",
        # Two @ signs, or a domain with no dot: not an address, left alone.
        f"{OID}a@b@contoso.com",
        f"{OID}justin.bell@localhost",
        # Not an address at all — some tenants stamp a bare name.
        "SYSTEM",
    ],
)
def test_anything_that_is_not_plainly_an_object_id_and_an_address_is_left_alone(upn):
    assert readable_upn(upn, resolved=False) == upn


def test_the_one_address_this_would_mangle_is_the_one_it_cannot_tell_apart():
    """Stated rather than hidden: an address whose local part *starts* with 32
    hex characters is indistinguishable from an object id glued to a shorter
    one, and this trims it.

    Nothing can separate those two by looking at the string. What keeps it safe
    is the guard above — it only ever runs on a creator Entra failed to resolve,
    and a person with a live mailbox at such an address resolves.
    """
    assert (
        readable_upn(f"{OID}abjustin.bell@contoso.com", resolved=False)
        == "abjustin.bell@contoso.com"
    )


def test_an_absent_address_stays_absent():
    assert readable_upn(None, resolved=False) is None
    assert readable_upn("", resolved=False) == ""
