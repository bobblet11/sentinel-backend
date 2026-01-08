import time 
import hashlib
import os

from logging import Logger, getLogger
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional
from common.constants.constants import BYTES_IN_ONE_MiB

MAX_SIZE_OF_SCREENSHOT_FOLDER: int = BYTES_IN_ONE_MiB * 512
GOAL_SIZE_OF_SCREENSHOT_FOLDER = int(MAX_SIZE_OF_SCREENSHOT_FOLDER * 0.5)

@dataclass(frozen=True)
class File:
	mtime:float
	file_size:int
	file_path:str
 
class RotatingScreenshotHandler():
        
	def __init__(self, screenshot_directory:Path | str = Path("/app/screenshots"), max_bytes: int = MAX_SIZE_OF_SCREENSHOT_FOLDER, goal_bytes:int = GOAL_SIZE_OF_SCREENSHOT_FOLDER) -> None:
		self.logger: Logger = getLogger(f"screenshot_handler")
		self.logger.info("--- Initializing ScreenshotHandler ---")
  
		if isinstance(screenshot_directory, str):
			screenshot_directory = Path(screenshot_directory)
		
		screenshot_directory.mkdir(mode=777, parents=True, exist_ok=True)
		self.screenshot_directory: Path = screenshot_directory
  
		self.max_bytes = max_bytes
		self.goal_bytes = goal_bytes
		self.current_bytes = 0

		self.remove_oldest_screenshots()
	
		self.logger.info("--- Initialized ScreenshotHandler ---")
	
	def remove_oldest_screenshots(self):
		total_size:int = 0
		files:List[File] = []
  
		for entry in os.scandir(str(self.screenshot_directory)):
			if entry.is_file() and entry.name.lower().endswith(".png"):
				st = entry.stat()
				total_size += st.st_size
				files.append(File(st.st_mtime, st.st_size, entry.path))
		
		files.sort(key=lambda file: file.mtime)
  
		self.current_bytes = total_size
  
		if total_size <= self.max_bytes:
			self.logger.debug(f"Directory {self.screenshot_directory} is not over {self.max_bytes}B")
			return
 
		for file in files:
			if total_size < self.goal_bytes:
				break
			
			try:
				os.unlink(file.file_path)
				total_size -= file.file_size
    
			except FileNotFoundError:
				self.logger.error(f"Screenshot {file.file_path} not found!")

	def save_screenshot(self, png_data: bytes, filename:Optional[str]) -> None:
		try:
			while self.current_bytes + len(png_data) >= self.max_bytes:
				self.logger.info("Too many bytes in screenshot directory! Trimming screenshots...")
				self.remove_oldest_screenshots()

			self.logger.debug("Saving screenshot")
   
			if not filename:
				timestamp: int = int(time.time())
				image_hash: str = hashlib.md5(png_data.encode("utf-8")).hexdigest()[:8]
				filename = f"{timestamp}_{image_hash}.png"

			file_path:Path = self.screenshot_directory / filename
			file_path.write_bytes(png_data)
			os.chmod(str(file_path), 0o666) 
			self.logger.info(f"📸 Screenshot saved to: {file_path}")
		except Exception as e:
			self.logger.error(f"Failed to write screenshot file: {e}")
			raise e
