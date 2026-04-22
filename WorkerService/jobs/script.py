import argparse

def main():
    parser = argparse.ArgumentParser(description="Demo job script")

    parser.add_argument("--name", default="default")
    parser.add_argument("--count", type=int, default=1)

    args = parser.parse_args()

    for i in range(args.count):
        print(f"[{i+1}] Hello {args.name}")

    print("Job finished successfully.")

if __name__ == "__main__":
    main()