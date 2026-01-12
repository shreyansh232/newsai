from app.runner import run_scrapers

def main(hours: int = 72):
        results = run_scrapers(hours=hours)
    
        print(f"\n=== Scraping Results (last {hours} hours) ===")
        print(f"YouTube videos: {len(results['youtube'])}")
        print(f"OpenAI articles: {len(results['openai'])}")
        print(f"Anthropic articles: {len(results['anthropic'])}")
    
        return results

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        hours = int(sys.argv[1])
        main(hours=hours)
    else:
        main()  # Uses default 72