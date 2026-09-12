"""Research CLI. See docs/BUILD_ARROW_03.md."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from research.arrow3 import run_arrow3  # noqa: E402
from research.arrow4 import run_arrow4  # noqa: E402
from research.arrow5 import run_arrow5  # noqa: E402
from research.arrow6 import run_arrow6  # noqa: E402
from research.arrow7 import run_arrow7  # noqa: E402
from research.arrow8 import run_arrow8  # noqa: E402
from research.arrow9 import run_arrow9  # noqa: E402
from research.arrow10 import run_arrow10  # noqa: E402
from research.arrow11 import run_arrow11  # noqa: E402
from research.arrow12 import run_arrow12  # noqa: E402
from research.arrow13 import run_arrow13  # noqa: E402
from research.arrow14 import run_arrow14  # noqa: E402
from research.arrow15 import run_arrow15  # noqa: E402
from ingest.full import run_arrow17  # noqa: E402
from ingest.virgin import run_arrow41, run_arrow61, run_arrow67, run_arrow69  # noqa: E402
from ingest.sic import run_arrow63  # noqa: E402
from research.arrow16 import run_arrow16  # noqa: E402
from research.arrow18 import run_arrow18  # noqa: E402
from research.arrow19 import run_arrow19  # noqa: E402
from research.arrow20 import run_arrow20  # noqa: E402
from research.arrow21 import run_arrow21  # noqa: E402
from research.arrow22 import run_arrow22  # noqa: E402
from research.arrow23 import run_arrow23  # noqa: E402
from research.arrow24 import run_arrow24  # noqa: E402
from research.arrow25 import run_arrow25  # noqa: E402
from research.arrow26 import run_arrow26  # noqa: E402
from research.arrow27 import run_arrow27  # noqa: E402
from research.arrow28 import run_arrow28  # noqa: E402
from research.arrow29 import run_arrow29  # noqa: E402
from research.arrow30 import run_arrow30  # noqa: E402
from research.arrow31 import run_arrow31  # noqa: E402
from research.arrow32 import run_arrow32  # noqa: E402
from research.arrow33 import run_arrow33  # noqa: E402
from research.arrow34 import run_arrow34  # noqa: E402
from research.arrow35 import run_arrow35  # noqa: E402
from research.arrow36 import run_arrow36  # noqa: E402
from research.arrow37 import run_arrow37  # noqa: E402
from research.arrow38 import run_arrow38  # noqa: E402
from research.arrow40 import run_arrow40  # noqa: E402
from research.arrow42 import run_arrow42  # noqa: E402
from research.arrow43 import run_arrow43  # noqa: E402
from research.arrow44 import run_arrow44  # noqa: E402
from research.arrow45 import run_arrow45  # noqa: E402
from research.arrow46 import run_arrow46  # noqa: E402
from research.arrow47 import run_arrow47  # noqa: E402
from research.arrow48 import run_arrow48  # noqa: E402
from research.arrow49 import run_arrow49  # noqa: E402
from research.arrow50 import run_arrow50  # noqa: E402
from research.arrow51 import run_arrow51  # noqa: E402
from research.arrow52 import run_arrow52  # noqa: E402
from research.arrow53 import run_arrow53  # noqa: E402
from research.arrow54 import run_arrow54  # noqa: E402
from research.arrow55 import run_arrow55  # noqa: E402
from research.arrow56 import run_arrow56  # noqa: E402
from research.arrow57 import run_arrow57  # noqa: E402
from research.arrow58 import run_arrow58  # noqa: E402
from research.arrow59 import run_arrow59  # noqa: E402
from research.arrow60 import run_arrow60  # noqa: E402
from research.arrow62 import run_arrow62  # noqa: E402
from research.arrow64 import run_arrow64  # noqa: E402
from research.arrow65 import run_arrow65  # noqa: E402
from research.arrow66 import run_arrow66  # noqa: E402
from research.arrow68 import run_arrow68  # noqa: E402
from research.arrow70 import run_arrow70  # noqa: E402
from research.arrow71 import run_arrow71  # noqa: E402
from research.arrow72 import run_arrow72  # noqa: E402
from research.arrow73 import run_arrow73  # noqa: E402
from research.arrow74 import run_arrow74  # noqa: E402
from research.arrow75 import run_arrow75  # noqa: E402
from research.arrow76 import run_arrow76  # noqa: E402
from research.arrow77 import run_arrow77  # noqa: E402
from research.arrow78 import run_arrow78  # noqa: E402
from research.arrow79 import run_arrow79  # noqa: E402
from research.arrow80 import run_arrow80  # noqa: E402
from research.equity_curve import run_equity_curve  # noqa: E402
from research.rockets import run_rockets  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    cpu = os.cpu_count() or 1
    p = argparse.ArgumentParser(description="Lab A research replay")
    p.add_argument(
        "--mode",
        choices=(
            "arrow3",
            "arrow4",
            "arrow5",
            "arrow6",
            "arrow7",
            "arrow8",
            "arrow9",
            "arrow10",
            "arrow11",
            "arrow12",
            "arrow13",
            "arrow14",
            "arrow15",
            "arrow16",
            "arrow17",
            "arrow18",
            "arrow19",
            "arrow20",
            "arrow21",
            "arrow22",
            "arrow23",
            "arrow24",
            "arrow25",
            "arrow26",
            "arrow27",
            "arrow28",
            "arrow29",
            "arrow30",
            "arrow31",
            "arrow32",
            "arrow33",
            "arrow34",
            "arrow35",
            "arrow36",
            "arrow37",
            "arrow38",
            "arrow40",
            "arrow41",
            "arrow42",
            "arrow61",
            "arrow43",
            "arrow44",
            "arrow45",
            "arrow46",
            "arrow47",
            "arrow48",
            "arrow49",
            "arrow50",
            "arrow51",
            "arrow52",
            "arrow53",
            "arrow54",
            "arrow55",
            "arrow56",
            "arrow57",
            "arrow58",
            "arrow59",
            "arrow60",
            "arrow62",
            "arrow63",
            "arrow64",
            "arrow65",
            "arrow66",
            "arrow67",
            "arrow68",
            "arrow69",
            "arrow70",
            "arrow71",
            "arrow72",
            "arrow73",
            "arrow74",
            "arrow75",
            "arrow76",
            "arrow77",
            "arrow78",
            "arrow79",
            "arrow80",
            "equity",
            "rockets",
        ),
        default="arrow80",
        help="arrow80 five frozen open leftover year books",
    )
    p.add_argument("--workers", type=int, default=min(8, cpu), help="default min(8, cpu_count)")
    args = p.parse_args(argv)
    if args.mode == "arrow3":
        return run_arrow3(workers=args.workers)
    if args.mode == "arrow4":
        return run_arrow4(workers=args.workers)
    if args.mode == "arrow5":
        return run_arrow5(workers=args.workers)
    if args.mode == "arrow6":
        return run_arrow6(workers=args.workers)
    if args.mode == "arrow7":
        return run_arrow7(workers=args.workers)
    if args.mode == "arrow8":
        return run_arrow8(workers=args.workers)
    if args.mode == "arrow9":
        return run_arrow9(workers=args.workers)
    if args.mode == "arrow10":
        return run_arrow10(workers=args.workers)
    if args.mode == "arrow11":
        return run_arrow11(workers=args.workers)
    if args.mode == "arrow12":
        return run_arrow12(workers=args.workers)
    if args.mode == "arrow13":
        return run_arrow13(workers=args.workers)
    if args.mode == "arrow14":
        return run_arrow14(workers=args.workers)
    if args.mode == "arrow15":
        return run_arrow15(workers=args.workers)
    if args.mode == "arrow16":
        return run_arrow16(workers=args.workers)
    if args.mode == "arrow17":
        return run_arrow17(workers=args.workers)
    if args.mode == "arrow18":
        return run_arrow18(workers=args.workers)
    if args.mode == "arrow19":
        return run_arrow19(workers=args.workers)
    if args.mode == "arrow20":
        return run_arrow20(workers=args.workers)
    if args.mode == "arrow21":
        return run_arrow21(workers=args.workers)
    if args.mode == "arrow22":
        return run_arrow22(workers=args.workers)
    if args.mode == "arrow23":
        return run_arrow23(workers=args.workers)
    if args.mode == "arrow24":
        return run_arrow24(workers=args.workers)
    if args.mode == "arrow25":
        return run_arrow25(workers=args.workers)
    if args.mode == "arrow26":
        return run_arrow26(workers=args.workers)
    if args.mode == "arrow27":
        return run_arrow27(workers=args.workers)
    if args.mode == "arrow28":
        return run_arrow28(workers=args.workers)
    if args.mode == "arrow29":
        return run_arrow29(workers=args.workers)
    if args.mode == "arrow30":
        return run_arrow30(workers=args.workers)
    if args.mode == "arrow31":
        return run_arrow31(workers=args.workers)
    if args.mode == "arrow32":
        return run_arrow32(workers=args.workers)
    if args.mode == "arrow33":
        return run_arrow33(workers=args.workers)
    if args.mode == "arrow34":
        return run_arrow34(workers=args.workers)
    if args.mode == "arrow35":
        return run_arrow35(workers=args.workers)
    if args.mode == "arrow36":
        return run_arrow36(workers=args.workers)
    if args.mode == "arrow37":
        return run_arrow37(workers=args.workers)
    if args.mode == "arrow38":
        return run_arrow38(workers=args.workers)
    if args.mode == "arrow40":
        return run_arrow40(workers=args.workers)
    if args.mode == "arrow41":
        return run_arrow41(workers=args.workers)
    if args.mode == "arrow61":
        return run_arrow61(workers=args.workers)
    if args.mode == "arrow42":
        return run_arrow42(workers=args.workers)
    if args.mode == "arrow43":
        return run_arrow43(workers=args.workers)
    if args.mode == "arrow44":
        return run_arrow44(workers=args.workers)
    if args.mode == "arrow45":
        return run_arrow45(workers=args.workers)
    if args.mode == "arrow46":
        return run_arrow46(workers=args.workers)
    if args.mode == "arrow47":
        return run_arrow47(workers=args.workers)
    if args.mode == "arrow48":
        return run_arrow48(workers=args.workers)
    if args.mode == "arrow49":
        return run_arrow49(workers=args.workers)
    if args.mode == "arrow50":
        return run_arrow50(workers=args.workers)
    if args.mode == "arrow51":
        return run_arrow51(workers=args.workers)
    if args.mode == "arrow52":
        return run_arrow52(workers=args.workers)
    if args.mode == "arrow53":
        return run_arrow53(workers=args.workers)
    if args.mode == "arrow54":
        return run_arrow54(workers=args.workers)
    if args.mode == "arrow55":
        return run_arrow55(workers=args.workers)
    if args.mode == "arrow56":
        return run_arrow56(workers=args.workers)
    if args.mode == "arrow57":
        return run_arrow57(workers=args.workers)
    if args.mode == "arrow58":
        return run_arrow58(workers=args.workers)
    if args.mode == "arrow59":
        return run_arrow59(workers=args.workers)
    if args.mode == "arrow60":
        return run_arrow60(workers=args.workers)
    if args.mode == "arrow62":
        return run_arrow62(workers=args.workers)
    if args.mode == "arrow63":
        return run_arrow63(workers=args.workers)
    if args.mode == "arrow64":
        return run_arrow64(workers=args.workers)
    if args.mode == "arrow65":
        return run_arrow65(workers=args.workers)
    if args.mode == "arrow66":
        return run_arrow66(workers=args.workers)
    if args.mode == "arrow67":
        return run_arrow67(workers=args.workers)
    if args.mode == "arrow68":
        return run_arrow68(workers=args.workers)
    if args.mode == "arrow69":
        return run_arrow69(workers=args.workers)
    if args.mode == "arrow70":
        return run_arrow70(workers=args.workers)
    if args.mode == "arrow71":
        return run_arrow71(workers=args.workers)
    if args.mode == "arrow72":
        return run_arrow72(workers=args.workers)
    if args.mode == "arrow73":
        return run_arrow73(workers=args.workers)
    if args.mode == "arrow74":
        return run_arrow74(workers=args.workers)
    if args.mode == "arrow75":
        return run_arrow75(workers=args.workers)
    if args.mode == "arrow76":
        return run_arrow76(workers=args.workers)
    if args.mode == "arrow77":
        return run_arrow77(workers=args.workers)
    if args.mode == "arrow78":
        return run_arrow78(workers=args.workers)
    if args.mode == "arrow79":
        return run_arrow79(workers=args.workers)
    if args.mode == "arrow80":
        return run_arrow80(workers=args.workers)
    if args.mode == "equity":
        return run_equity_curve(workers=args.workers)
    if args.mode == "rockets":
        return run_rockets(workers=args.workers)
    raise SystemExit(f"unknown mode {args.mode}")


if __name__ == "__main__":
    sys.exit(main())
