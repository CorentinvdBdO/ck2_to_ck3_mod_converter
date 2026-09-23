#!/usr/bin/env python3
"""Research prototype for docs/research_race_tooling.md — NOT wired into the
converter, NOT a converter step. Demonstrates that CK3's vanilla ethnicity
gene-weight format can be parsed and sampled into valid `common/dna_data`
entries, deterministically per a caller-supplied seed (e.g. a converter
character id), reusing the existing `ck2ck3.pdx` parser as-is (no new parser
invented, per the lane's "no converter step changes" rule).

What it does:
  1. Indexes every ethnicity block in `common/ethnicities/*.txt` (vanilla or
     any mod pointed at with --ethnicities-dir), resolving `@var` references
     per file (matches how vanilla scopes them: each ethnicity file redefines
     its own @neg1_min/@pos1_min/etc. rather than sharing a global table).
  2. Resolves one ethnicity's full gene-weight table by walking its
     `template =` / `using =` inheritance chain (later layer's key wins,
     same semantics Paradox script itself uses for an override-by-key merge).
  3. For each gene (3 color genes: 2D weighted range into a palette texture;
     every other key: a name + 1D weighted range, exactly the same shape
     whether the key is `gene_*`, `complexion`, or an eyebrow/hair-type
     table — the ethnicity format does not special-case gene kind), draws
     two independent alleles (dominant, recessive) with a per-character RNG
     seeded from `seed:index`, converts the sampled 0..1 float pair/value to
     the 0..255 integer form `common/dna_data` stores.
  4. Writes N such entries as a `common/dna_data`-format script file, with the
     UTF-8 BOM vanilla ships on every file in that folder.

Usage:
  uv run scripts/dna_parse.py --ethnicity mediterranean --count 5 --seed demo
  uv run scripts/dna_parse.py --ethnicity mediterranean --count 500 \
      --seed fae_run_1 --out /tmp/sample_dna.txt
  uv run scripts/dna_parse.py --list-ethnicities | head

Self-check: `uv run scripts/dna_parse.py --self-test` parses vanilla, samples
twice with the same seed, and asserts byte-identical output (determinism) and
a nonzero gene count (parser actually found the ethnicity's gene table).
"""

from __future__ import annotations

import argparse
import hashlib
import random
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from ck2ck3.pdx import nodes as pdx_nodes  # noqa: E402
from ck2ck3.pdx import parser as pdx_parser  # noqa: E402

DEFAULT_GAME_ROOT = REPO_ROOT.parent / "claudespace" / "game_files"
COLOR_GENES = ("skin_color", "hair_color", "eye_color")
SKIP_KEYS = {"template", "using", "visible"}
MAX_INHERITANCE_DEPTH = 8


class EthnicityIndexError(RuntimeError):
    pass


def index_ethnicities(ethnicities_dir: Path) -> dict[str, pdx_nodes.Block]:
    """Map every top-level ethnicity block name to its (resolved) Block.

    Two passes over every `*.txt` in the folder: (1) parse every file and
    collect every `@var = value` into one folder-wide table, sorted-filename
    order, later file wins a name clash; (2) resolve every document against
    that combined table. Needed because `@var` scope is **not** reliably
    per-file: vanilla's own `01_ethnicities_mediterranean.txt` redeclares
    `@neg1_min`/`@pos1_min`/etc. itself, but Elder Kings 2's
    `001_ek_ethnicities_beast_argonian.txt` uses the same names with **no**
    local declaration at all, reading them from `00_ethnicities_templates.txt`
    — a file that alphabetically sorts *after* it (`00_` follows `001_`
    lexicographically). A single global table, order aside, resolves both;
    a genuinely load-order-dependent redefinition would need real per-file
    streaming resolution, not attempted here (`assumed` not to matter for
    the vanilla/EK2/Godherja ethnicity files actually inspected).
    """
    docs: list[pdx_nodes.Document] = []
    var_table: dict[str, object] = {}
    for path in sorted(ethnicities_dir.glob("*.txt")):
        doc = pdx_parser.parse_file(path, lenient=True)
        docs.append(doc)
        var_table.update(pdx_nodes.variables(doc))
    blocks: dict[str, pdx_nodes.Block] = {}
    for doc in docs:
        resolved = pdx_nodes.resolve(doc, var_table)
        for entry in resolved.entries:
            if (
                isinstance(entry, pdx_nodes.Node)
                and isinstance(entry.value, pdx_nodes.Block)
                and not entry.key.startswith("@")
            ):
                blocks[entry.key] = entry.value
    return blocks


def _gene_entries(block: pdx_nodes.Block) -> dict[str, list[tuple[int, object]]]:
    """One ethnicity block's own (non-inherited) gene tables.

    Each gene key maps to a list of (weight, payload) pairs in source order:
    payload is a list[float] of length 4 for a color gene, or
    (name: str, min: float, max: float) for every other gene shape.
    """
    out: dict[str, list[tuple[int, object]]] = {}
    for entry in block.entries:
        if not isinstance(entry, pdx_nodes.Node) or entry.key in SKIP_KEYS:
            continue
        if entry.key.startswith("@") or not isinstance(entry.value, pdx_nodes.Block):
            continue
        weighted: list[tuple[int, object]] = []
        for sub in entry.value.entries:
            if not isinstance(sub, pdx_nodes.Node):
                continue
            try:
                weight = int(sub.key)
            except ValueError:
                continue  # not a weighted-table gene (skip non-gene sub-blocks)
            if entry.key in COLOR_GENES:
                vals = sub.value.list_values() if isinstance(sub.value, pdx_nodes.Block) else []
                if len(vals) != 4:
                    continue
                weighted.append((weight, [float(v) for v in vals]))
            else:
                if not isinstance(sub.value, pdx_nodes.Block):
                    continue
                name = sub.value.get("name")
                rng = sub.value.get("range")
                if name is None or not isinstance(rng, pdx_nodes.Block):
                    continue
                rng_vals = rng.list_values()
                if len(rng_vals) != 2:
                    continue
                weighted.append((weight, (str(name), float(rng_vals[0]), float(rng_vals[1]))))
        if weighted:
            out[entry.key] = weighted
    return out


def resolve_gene_table(
    name: str, index: dict[str, pdx_nodes.Block], *, _depth: int = 0
) -> dict[str, list[tuple[int, object]]]:
    """Full gene-weight table for `name`, inheritance chain applied.

    `template` supplies the base table, `using` layers another named
    ethnicity's table on top of that, and the block's own keys win last —
    each layer replaces a gene key wholesale (Paradox's own override
    semantics; ethnicity files never merge two weighted lists for one gene).
    """
    if _depth > MAX_INHERITANCE_DEPTH:
        raise EthnicityIndexError(f"ethnicity inheritance too deep at {name!r} (cycle?)")
    if name not in index:
        raise EthnicityIndexError(f"no ethnicity block named {name!r}")
    block = index[name]
    table: dict[str, list[tuple[int, object]]] = {}
    template = block.get("template")
    if template:
        if str(template) in index:
            table.update(resolve_gene_table(str(template), index, _depth=_depth + 1))
        else:
            print(f"warn: {name!r} template={template!r} not found in this install, skipping that layer", file=sys.stderr)
    using = block.get("using")
    if using:
        # verified vanilla 1.19 quirk: `mediterranean` declares `using = "basque"`
        # but no `basque` ethnicity block exists in this install (DLC-gated or
        # dead reference) — tolerate a missing `using` target rather than
        # crash, since the game itself evidently does (the file ships this
        # way). docs/research_race_tooling.md records it.
        if str(using) in index:
            table.update(resolve_gene_table(str(using), index, _depth=_depth + 1))
        else:
            print(f"warn: {name!r} using={using!r} not found in this install, skipping that layer", file=sys.stderr)
    table.update(_gene_entries(block))
    return table


def _weighted_choice(rng: random.Random, options: list[tuple[int, object]]) -> object:
    weights = [w for w, _ in options]
    if sum(weights) <= 0:
        raise EthnicityIndexError("gene table has no positive-weight entries")
    return rng.choices(options, weights=weights, k=1)[0][1]


def _to_byte(v: float) -> int:
    return max(0, min(255, round(v * 255)))


def sample_dna(
    gene_table: dict[str, list[tuple[int, object]]], seed_key: str
) -> dict[str, tuple]:
    """One character's DNA: two independent allele draws per gene.

    Deterministic in `seed_key` alone — same key always yields the same DNA,
    regardless of call order or how many other characters are sampled in the
    same run (the "deterministic seed per character" requirement of
    `docs/design_races.md`'s mass-character-creation step).
    """
    digest = hashlib.sha256(seed_key.encode("utf-8")).digest()
    rng = random.Random(int.from_bytes(digest[:8], "big"))
    genes: dict[str, tuple] = {}
    for gene, options in gene_table.items():
        if gene in COLOR_GENES:
            allele_a = _weighted_choice(rng, options)
            allele_b = _weighted_choice(rng, options)
            xa = rng.uniform(allele_a[0], allele_a[2])
            ya = rng.uniform(allele_a[1], allele_a[3])
            xb = rng.uniform(allele_b[0], allele_b[2])
            yb = rng.uniform(allele_b[1], allele_b[3])
            genes[gene] = ("color", _to_byte(xa), _to_byte(ya), _to_byte(xb), _to_byte(yb))
        else:
            name_a, lo_a, hi_a = _weighted_choice(rng, options)
            name_b, lo_b, hi_b = _weighted_choice(rng, options)
            va = _to_byte(rng.uniform(lo_a, hi_a))
            vb = _to_byte(rng.uniform(lo_b, hi_b))
            genes[gene] = ("morph", name_a, va, name_b, vb)
    return genes


def format_dna_entry(char_id: str, genes: dict[str, tuple]) -> str:
    lines = [f"{char_id} = {{", "\tportrait_info = {", "\t\tgenes={"]
    for gene, payload in genes.items():
        if payload[0] == "color":
            _, xa, ya, xb, yb = payload
            lines.append(f"\t\t\t{gene}={{ {xa} {ya} {xb} {yb} }}")
        else:
            _, name_a, va, name_b, vb = payload
            lines.append(f'\t\t\t{gene}={{ "{name_a}" {va} "{name_b}" {vb} }}')
    lines += ["\t\t}", "\t}", "}"]
    return "\n".join(lines)


def build_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--game-root", type=Path, default=DEFAULT_GAME_ROOT, help="CK3 game/ dir (vanilla, read-only)")
    p.add_argument("--ethnicities-dir", type=Path, default=None, help="override: a common/ethnicities/ dir directly")
    p.add_argument("--ethnicity", default="mediterranean", help="ethnicity block name to sample from")
    p.add_argument("--count", type=int, default=5, help="how many DNA entries to generate")
    p.add_argument("--seed", default="dna_parse_demo", help="base seed; DNA is deterministic in seed+index")
    p.add_argument("--prefix", default="fae_dna_sample", help="generated character-id prefix")
    p.add_argument("--out", type=Path, default=None, help="write dna_data-format script here (else print)")
    p.add_argument("--list-ethnicities", action="store_true", help="print every indexed ethnicity name and exit")
    p.add_argument("--self-test", action="store_true", help="run the determinism/sanity check and exit")
    return p.parse_args()


def _ethnicities_dir(args: argparse.Namespace) -> Path:
    d = args.ethnicities_dir or (args.game_root / "common" / "ethnicities")
    if not d.is_dir():
        raise SystemExit(f"not a directory: {d} (pass --game-root or --ethnicities-dir)")
    return d


def self_test() -> None:
    class A:
        game_root = DEFAULT_GAME_ROOT
        ethnicities_dir = None
    d = _ethnicities_dir(A())
    index = index_ethnicities(d)
    assert "mediterranean" in index, "expected vanilla ethnicity 'mediterranean' not found"
    table = resolve_gene_table("mediterranean", index)
    assert len(table) >= 90, f"expected ~100 inherited genes, got {len(table)}"
    assert "skin_color" in table and "hair_color" in table and "eye_color" in table
    out_a = format_dna_entry("x", sample_dna(table, "seed_A:0"))
    out_b = format_dna_entry("x", sample_dna(table, "seed_A:0"))
    assert out_a == out_b, "same seed key produced different DNA (not deterministic)"
    out_c = format_dna_entry("x", sample_dna(table, "seed_A:1"))
    assert out_a != out_c, "different seed key produced identical DNA (suspiciously coupled)"
    # round-trip: the emitted text must itself parse as valid Paradox script,
    # with a genes block that has one entry per resolved gene (a syntax bug
    # or a truncated gene name would show up as a count mismatch here).
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8-sig") as f:
        f.write(out_a + "\n")
        tmp_path = Path(f.name)
    try:
        reparsed = pdx_parser.parse_file(tmp_path)
        genes_block = reparsed["x"]["portrait_info"]["genes"]
        assert len(genes_block.keys()) == len(table), (
            f"round-trip gene count mismatch: wrote {len(table)}, reparsed {len(genes_block.keys())}"
        )
    finally:
        tmp_path.unlink(missing_ok=True)
    print(f"self-test OK: {len(index)} ethnicities indexed, "
          f"'mediterranean' resolves {len(table)} genes, sampling is deterministic per seed key, "
          f"emitted script round-trips through the real parser")


def main() -> None:
    args = build_args()
    if args.self_test:
        self_test()
        return
    d = _ethnicities_dir(args)
    index = index_ethnicities(d)
    if args.list_ethnicities:
        for name in sorted(index):
            print(name)
        return
    table = resolve_gene_table(args.ethnicity, index)
    entries = []
    for i in range(args.count):
        char_id = f"{args.prefix}_{i}"
        genes = sample_dna(table, f"{args.seed}:{char_id}")
        entries.append(format_dna_entry(char_id, genes))
    text = "\n".join(entries) + "\n"
    if args.out:
        args.out.write_text(text, encoding="utf-8-sig")  # dna_data files carry a BOM
        print(f"wrote {args.count} DNA entries ({len(table)} genes each) to {args.out}")
    else:
        print(text)


if __name__ == "__main__":
    main()
