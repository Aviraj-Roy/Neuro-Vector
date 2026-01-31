"""
CLI Tool: Pre-build Embeddings

Pre-generates and caches embeddings for all tie-up rate sheet data.
Run this ONCE after adding/updating tie-up JSON files to avoid
consuming API quota during normal operation.

Usage:
    python -m app.tools.build_embeddings
    python -m app.tools.build_embeddings --tieup-dir data/tieups
    python -m app.tools.build_embeddings --clear-cache

Options:
    --tieup-dir DIR    Directory containing tie-up JSON files (default: data/tieups)
    --clear-cache      Clear existing cache before building
    --dry-run          Show what would be embedded without calling API
    --verbose          Enable verbose logging
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
load_dotenv()


def setup_logging(verbose: bool = False):
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%H:%M:%S"
    )


def collect_all_texts(rate_sheets) -> dict:
    """
    Collect all text strings that need embeddings.
    
    Returns dict with counts by category.
    """
    texts = {
        "hospitals": [],
        "categories": [],
        "items": []
    }
    
    for rs in rate_sheets:
        texts["hospitals"].append(rs.hospital_name)
        
        for cat in rs.categories:
            texts["categories"].append(cat.category_name)
            
            for item in cat.items:
                texts["items"].append(item.item_name)
    
    return texts


def main():
    parser = argparse.ArgumentParser(
        description="Pre-build embeddings for tie-up rate sheets"
    )
    parser.add_argument(
        "--tieup-dir",
        default=os.getenv("TIEUP_DATA_DIR", "data/tieups"),
        help="Directory containing tie-up JSON files"
    )
    parser.add_argument(
        "--clear-cache",
        action="store_true",
        help="Clear existing cache before building"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be embedded without calling API"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )
    
    args = parser.parse_args()
    setup_logging(args.verbose)
    
    logger = logging.getLogger(__name__)
    
    print("=" * 60)
    print("Embedding Pre-Builder")
    print("=" * 60)
    
    # Check for API key
    if not args.dry_run and not os.getenv("OPENAI_API_KEY"):
        print("\nERROR: OPENAI_API_KEY not set!")
        print("Set it in .env file or environment variable.")
        sys.exit(1)
    
    # Import after env setup
    from app.verifier.verifier import load_all_tieups
    from app.verifier.embedding_service import get_embedding_service
    from app.verifier.embedding_cache import get_embedding_cache
    
    # Load tie-up rate sheets
    print(f"\n1. Loading tie-up rate sheets from: {args.tieup_dir}")
    rate_sheets = load_all_tieups(args.tieup_dir)
    
    if not rate_sheets:
        print("ERROR: No rate sheets found!")
        sys.exit(1)
    
    print(f"   Found {len(rate_sheets)} rate sheets:")
    for rs in rate_sheets:
        cat_count = len(rs.categories)
        item_count = sum(len(cat.items) for cat in rs.categories)
        print(f"   - {rs.hospital_name}: {cat_count} categories, {item_count} items")
    
    # Collect all texts
    print("\n2. Collecting texts to embed...")
    texts = collect_all_texts(rate_sheets)
    
    # Deduplicate
    all_texts = set()
    all_texts.update(texts["hospitals"])
    all_texts.update(texts["categories"])
    all_texts.update(texts["items"])
    
    print(f"   Hospitals: {len(texts['hospitals'])}")
    print(f"   Categories: {len(texts['categories'])} ({len(set(texts['categories']))} unique)")
    print(f"   Items: {len(texts['items'])} ({len(set(texts['items']))} unique)")
    print(f"   Total unique texts: {len(all_texts)}")
    
    if args.dry_run:
        print("\n[DRY RUN] Would embed the following texts:")
        for i, text in enumerate(sorted(all_texts)[:20]):
            print(f"   {i+1}. {text}")
        if len(all_texts) > 20:
            print(f"   ... and {len(all_texts) - 20} more")
        print("\nDry run complete. No API calls made.")
        return
    
    # Get services
    cache = get_embedding_cache()
    service = get_embedding_service()
    
    # Clear cache if requested
    if args.clear_cache:
        print("\n3. Clearing existing cache...")
        cache.clear()
        print("   Cache cleared.")
    else:
        print(f"\n3. Current cache size: {cache.size} embeddings")
    
    # Check what's already cached
    texts_to_embed = []
    cached_count = 0
    
    for text in all_texts:
        if cache.contains(text):
            cached_count += 1
        else:
            texts_to_embed.append(text)
    
    print(f"   Already cached: {cached_count}")
    print(f"   Need to embed: {len(texts_to_embed)}")
    
    if not texts_to_embed:
        print("\n✓ All embeddings already cached. Nothing to do!")
        return
    
    # Embed in batches
    print(f"\n4. Generating embeddings for {len(texts_to_embed)} texts...")
    
    batch_size = service.max_batch_size
    total_batches = (len(texts_to_embed) + batch_size - 1) // batch_size
    
    success_count = 0
    error_count = 0
    
    for i in range(0, len(texts_to_embed), batch_size):
        batch = texts_to_embed[i:i + batch_size]
        batch_num = i // batch_size + 1
        
        print(f"   Batch {batch_num}/{total_batches} ({len(batch)} texts)...", end=" ")
        
        try:
            embeddings, error = service.get_embeddings_safe(batch)
            
            if error:
                print(f"ERROR: {error}")
                error_count += len(batch)
            else:
                print("OK")
                success_count += len(batch)
                
        except KeyboardInterrupt:
            print("\n\nInterrupted by user. Saving cache...")
            cache.save()
            print(f"Cache saved with {cache.size} embeddings.")
            sys.exit(1)
        except Exception as e:
            print(f"ERROR: {e}")
            error_count += len(batch)
    
    # Save cache
    print("\n5. Saving cache to disk...")
    if cache.save():
        print(f"   ✓ Saved {cache.size} embeddings to {cache.cache_path}")
    else:
        print("   ERROR: Failed to save cache!")
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Successfully embedded: {success_count}")
    print(f"Errors: {error_count}")
    print(f"Total cached: {cache.size}")
    
    if error_count > 0:
        print("\n⚠ Some embeddings failed. Re-run to retry.")
        sys.exit(1)
    else:
        print("\n✓ All embeddings built successfully!")
        print("  The verifier will now use cached embeddings.")


if __name__ == "__main__":
    main()
