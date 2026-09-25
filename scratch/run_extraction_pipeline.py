"""
Run the extraction pipeline over all files in data/regulatory_policies_v2/
"""
import os
import glob
import json
import logging
from core.generator import Generator
from services.extractor import extract_rules

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    source_dir = r"c:\acm hackathon\MarketSphere\data\regulatory_policies_v2"
    output_file = r"c:\acm hackathon\MarketSphere\data\extracted_15_countries_rules.v3_pipeline.json"

    # Ensure Generator uses the correct ollama host if necessary, but defaults should work
    llm_client = Generator()

    files = glob.glob(os.path.join(source_dir, "*.txt"))
    files.sort()

    all_rules = []

    for file_path in files:
        filename = os.path.basename(file_path)
        logger.info("Processing %s...", filename)
        
        with open(file_path, "r", encoding="utf-8") as f:
            chunk_text = f.read()

        # The extracted rules come back as a list of CandidateRule objects
        try:
            rules = extract_rules(
                chunk_text=chunk_text,
                source_id=filename,
                llm_client=llm_client,
                raise_on_hallucination=False
            )
            
            for rule in rules:
                rule_dict = rule.model_dump()
                # The pipeline sets evidence_tag appropriately in the judge phase
                all_rules.append(rule_dict)
                
            logger.info("  Extracted %d rules from %s", len(rules), filename)
        except Exception as e:
            logger.error("  Error processing %s: %s", filename, e)

    logger.info("Total rules extracted: %d", len(all_rules))

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_rules, f, indent=2)

    logger.info("Saved to %s", output_file)

if __name__ == "__main__":
    main()
