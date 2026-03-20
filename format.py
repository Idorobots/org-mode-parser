#!/usr/bin/env python3

import sys
import org_parser


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} FILE")
    else:
       document = org_parser.load(sys.argv[1])
       document.reformat()
       print(org_parser.dumps(document))
