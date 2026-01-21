import logging
import torch
from typing import Any, List

# Local imports
from models.base import NLPComponent
from schemas import ArticleInput, AnalysisResult, AnalysisOptions

logger = logging.getLogger(__name__)

class Decontextualizer(NLPComponent):
    """
    Rewrites sentences to be self-contained by resolving coreferences 
    (e.g., "He said" -> "Biden said") using a sliding window of previous sentences as context.
    
    Model: google/flan-t5-base
    Strategy: Sliding Window (Lookback 3 sentences)
    """
    def __init__(self, rewriter_model: Any = None, tokenizer: Any = None):
        """
        Args:
            rewriter_model: Loaded AutoModelForSeq2SeqLM (optional, can load on init)
            tokenizer: Loaded AutoTokenizer (optional)
        """
        self.model = rewriter_model
        self.tokenizer = tokenizer
        self.window_size = 3  # How many previous sentences to use as context
        
        # Load model if not provided (Standard production setup)
        if not self.model or not self.tokenizer:
            logger.info("Decontextualizer: No model provided. Loading default 'google/flan-t5-base'...")
            try:
                from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
                model_name = "google/flan-t5-base"
                self.tokenizer = AutoTokenizer.from_pretrained(model_name)
                self.model = AutoModelForSeq2SeqLM.from_pretrained(model_name)
                
                if torch.cuda.is_available():
                    self.model = self.model.to("cuda")
                    logger.info("Decontextualizer: Loaded on GPU (CUDA).")
                else:
                    logger.info("Decontextualizer: Loaded on CPU.")
            except Exception as e:
                logger.error(f"Decontextualizer: Failed to load model: {e}")
                raise

    def run(self, article: ArticleInput, result: AnalysisResult, options: AnalysisOptions) -> None:
        """
        Iterates through sentences and rewrites them using previous sentences as context.
        Updates result.sentences[i].text in-place.
        """
        # Validation
        if not result.sentences:
            logger.warning("Decontextualizer: No sentences to process.")
            return

        logger.info(f"Decontextualizer: Processing {len(result.sentences)} sentences...")
        
        # Extract just the text strings for easier indexing during the window lookback
        raw_texts = [s.text for s in result.sentences]
        
        # We assume the model is on the correct device
        device = self.model.device

        for i, sentence_obj in enumerate(result.sentences):
            current_text = sentence_obj.text
            
            # Skip very short sentences (often titles or garbage) to save compute
            if len(current_text) < 15:
                continue

            # 1. Build Context (Sliding Window)
            # Grab the previous 'window_size' sentences
            start_idx = max(0, i - self.window_size)
            # Join previous sentences with spaces
            context_text = " ".join(raw_texts[start_idx:i])
            
            # Handle first sentence case
            if not context_text:
                context_text = "Start of article."

            # 2. Construct Prompt
            # Explicit instruction is crucial for T5
            input_prompt = (
                f"Context: {context_text}\n\n"
                f"Sentence: {current_text}\n\n"
                f"Rewrite the sentence to replace pronouns (he, she, it, they) "
                f"and generic terms with specific names from the context. "
                f"If no change is needed, output the original sentence.\n\n"
                f"Rewritten:"
            )

            # 3. Inference
            try:
                inputs = self.tokenizer(input_prompt, return_tensors="pt", max_length=512, truncation=True).to(device)
                
                outputs = self.model.generate(
                    inputs.input_ids,
                    max_length=128,
                    num_beams=4, # Beam search for better quality
                    early_stopping=True
                )
                
                new_text = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
                
                # 4. Quality Gate & Update
                # Only update if the text changed and didn't collapse (safety check)
                if new_text.lower() != current_text.lower():
                    # Sanity check: Don't accept if text shrank drastically (model failure)
                    if len(new_text) > len(current_text) * 0.5: 
                        # Update the original text in the result object
                        sentence_obj.text = new_text
                        # logger.debug(f"Rewrote: '{current_text}' -> '{new_text}'")

            except Exception as e:
                logger.error(f"Decontext failed on sentence {i}: {e}")
                # On failure, we silently keep the original text and continue
                continue
        
        logger.info("Decontextualizer: Completed.")