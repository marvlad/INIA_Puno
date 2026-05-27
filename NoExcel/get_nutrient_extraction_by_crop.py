# get_nutrient_extraction_by_crop.py

import argparse

from nutrient_extraction import print_nutrient_extraction_table


def main():
    parser = argparse.ArgumentParser(
        description="Get nutrient extraction table by crop name."
    )

    parser.add_argument(
        "--cultivo",
        required=True,
        help="Crop name, example: OLIVO, ALFALFA, PAPA NATIVA",
    )

    args = parser.parse_args()

    print_nutrient_extraction_table(args.cultivo)


if __name__ == "__main__":
    main()
