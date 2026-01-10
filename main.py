from app.runner import run_scrapers

def main(hours: int = 24):
        results = run_scrapers(hours=hours)
    
        print(f"\n=== Scraping Results (last {hours} hours) ===")
        print(f"YouTube videos: {len(results['youtube'])}")
        print(f"OpenAI articles: {len(results['openai'])}")
        print(f"Anthropic articles: {len(results['anthropic'])}")
    
        return results

if __name__ == "__main__":
    import sys
    hours = int(sys.argv[1]) if len(sys.argv) > 1 else 24
    main(hours=hours)