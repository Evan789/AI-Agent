def main() -> None:
    import uvicorn

    from yxbot.app import create_app

    uvicorn.run(create_app(), host="127.0.0.1", port=8766)


if __name__ == "__main__":
    main()
