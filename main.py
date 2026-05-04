import asyncio
import sys
from client_runner import ClientRunner
from logger import setup_logger

logger = setup_logger("main")

async def main():
    logger.info("Starting Endra Bot...")
    try:
        runner = ClientRunner()
        await runner.run()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
    except Exception as e:
        logger.critical(f"Unhandled exception: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
