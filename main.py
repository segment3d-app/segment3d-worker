import logging
import asyncio

from dotenv import load_dotenv


def main():
    async def task():
        logging.info("Running tasks...")

        await asyncio.sleep(5)
        logging.info("Tasks run successfuly!")

    asyncio.run(task())


if __name__ == "__main__":
    load_dotenv()

    log_format = "%(asctime)s [%(levelname)s]: (%(name)s) %(message)s"
    logging.basicConfig(level=logging.INFO, format=log_format)

    main()
