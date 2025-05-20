import requests
from bs4 import BeautifulSoup
import time
import random
import pandas as pd # Make sure pandas is installed: pip install pandas
import re # For cleaning text

def clean_text_for_csv(text):
    """Cleans text by removing excessive whitespace and normalizing newlines."""
    if not text:
        return ""
    text = re.sub(r'\s*\n\s*', ' ', text.strip()) # Replace newlines with a space for these fields
    text = re.sub(r'[ \t]+', ' ', text)
    return text.strip()

def get_linkedin_jobs_fast(search_url, num_pages_to_try=1):
    """
    Fetches job Title, Company, Location, and URL directly from search results pages.
    Skips visiting individual job pages for speed.
    """
    all_jobs_data = []
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.60 Safari/537.36', # Updated User-Agent
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive'
    }
    
    # Try to determine parameters for pagination from the provided search_url
    # This is a simplified approach. More robust URL parsing might be needed.
    base_url_for_pagination = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
    try:
        url_params = dict(qc.split("=") for qc in search_url.split("?")[1].split("&"))
        keywords = url_params.get('keywords', 'product%20design%20engineer%20mechanical%20engineering')
        geoId = url_params.get('geoId', '103644278') # Default US geoId
        location_name = url_params.get('location', 'United%20States') # Or parse from geoId if possible
    except Exception:
        print("Could not parse keywords/geoId/location from initial URL for pagination. Using defaults.")
        keywords = "product%20design%20engineer%20mechanical%20engineering"
        geoId = "103644278"
        location_name = "United%20States"


    print(f"Starting fast job scraping for keywords: {keywords.replace('%20', ' ')}")

    for page_num in range(num_pages_to_try):
        start_index = page_num * 25 # LinkedIn typically shows 25 jobs per 'page' or API call
        
        # For the first page, try to use the direct search URL if it looks like one,
        # otherwise, or for subsequent pages, use the guest API structure.
        if page_num == 0 and "linkedin.com/jobs/search/" in search_url and not "api/seeMoreJobPostings" in search_url:
            current_url = search_url
            print(f"Fetching initial search results page: {current_url}")
        else:
            # Construct URL for the guest API
            # Note: 'f_TPR=r86400' (last 24h) or other filters might be useful.
            # The 'location' param for the API usually wants the text name.
            current_url = f"{base_url_for_pagination}?keywords={keywords}&location={location_name}&geoId={geoId}&start={start_index}"
            if "f_TPR" in url_params: # carry over time filter if present
                current_url += f"&f_TPR={url_params['f_TPR']}"
            print(f"Fetching jobs (page {page_num + 1}) via API: {current_url}")

        try:
            response = requests.get(current_url, headers=headers, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Selectors for job cards might vary depending on whether it's a direct search page or API response
            job_cards = soup.find_all('div', class_=['base-search-card', 'job-search-card']) # Common classes for job cards
            if not job_cards: # Fallback for API responses which often use <li>
                 job_cards = soup.find_all('li', class_=['job-result-card', 'job-search-card__list-item'])
            if not job_cards: # More generic list item
                job_cards = soup.find_all('li')


            print(f"Found {len(job_cards)} potential job cards on page {page_num + 1}.")
            if not job_cards and page_num > 0:
                print(f"No job cards found on page {page_num + 1}. The API structure or selectors might have changed.")

            page_jobs_count = 0
            for card in job_cards:
                # Try various selectors, as LinkedIn's structure can be inconsistent
                job_title_element = card.find('h3', class_=['base-search-card__title', 'job-result-card__title'])
                job_company_element = card.find('h4', class_=['base-search-card__subtitle', 'job-result-card__subtitle'])
                job_location_element = card.find('span', class_=['job-search-card__location', 'job-result-card__location'])
                
                # For the job link, it's often an <a> tag wrapping the card or title
                job_link_element = card.find('a', class_=['base-card__full-link', 'job-result-card__card-link'])
                if not job_link_element: # If the main link isn't found, try within the title
                    if job_title_element:
                        job_link_element = job_title_element.find('a')
                if not job_link_element: # Fallback to any link within the card (might not always be the job link)
                    job_link_element = card.find('a', href=True)


                job_title = clean_text_for_csv(job_title_element.text) if job_title_element else None
                company_name = clean_text_for_csv(job_company_element.text) if job_company_element else None
                location = clean_text_for_csv(job_location_element.text) if job_location_element else None
                job_url = job_link_element['href'].split('?')[0] if job_link_element and job_link_element.has_attr('href') else None # Get base URL

                # Ensure URL is absolute
                if job_url and "linkedin.com" not in job_url:
                    if job_url.startswith("/jobs/view/"):
                        job_url = f"https://www.linkedin.com{job_url}"
                    # Add other heuristics if needed for relative URLs from different contexts

                if job_title and company_name and job_url: # Require these essential fields
                    all_jobs_data.append({
                        'Title': job_title,
                        'Company': company_name,
                        'Location': location,
                        'URL': job_url
                    })
                    page_jobs_count += 1
            
            if page_jobs_count == 0 and len(job_cards) > 0:
                print(f"Could not extract structured job data despite finding {len(job_cards)} cards. Selectors might be outdated.")
            elif page_jobs_count > 0:
                print(f"Successfully extracted {page_jobs_count} jobs from this page.")


            # Respectful scraping: add a delay
            time.sleep(random.uniform(1, 3)) # Shorter delay as we are not hitting as many pages per job

            if page_jobs_count == 0 and page_num > 0 : # If subsequent pages yield no structured data, stop.
                 print(f"Stopping pagination attempt as page {page_num+1} yielded no structured jobs.")
                 break

        except requests.exceptions.RequestException as e:
            print(f"Request failed for {current_url}: {e}")
            # Optionally, you could retry or log this URL
            break # Stop on request failure for this example
        except Exception as e:
            print(f"An error occurred while processing page {page_num + 1}: {e}")
            # You might want to log the HTML content here for debugging if parsing fails
            # with open(f"error_page_{page_num}.html", "w", encoding="utf-8") as f_err:
            # f_err.write(soup.prettify())
            continue 
            
    return all_jobs_data


if __name__ == "__main__":
    # The URL from your question, good for getting initial parameters
    linkedin_search_url_template = "https://www.linkedin.com/jobs/search/?keywords={keywords}&location={location}&geoId={geoId}&f_TPR=r86400" # f_TPR=r86400 is for "Past 24 hours"

    # Example: Scrape for "Software Engineer" jobs in "New York City, NY" (geoId for NYC is approx 101165590)
    # Use a general search URL to start, rather than one with a currentJobId if you want a broad scrape.
    keywords_query = "product design engineer mechanical engineering"
    location_query = "United States" # Location name for the API
    geoId_query = "103644278"       # geoId for US
    # Update this to your specific search if needed:
    # user_initial_search_url = "https://www.linkedin.com/jobs/search/?keywords=product%20design%20engineer%20mechanical%20engineering&location=United%20States&geoId=103644278&refresh=true"
    
    # For more targeted initial URL:
    user_initial_search_url = linkedin_search_url_template.format(
        keywords=keywords_query.replace(" ", "%20"),
        location=location_query.replace(" ", "%20"),
        geoId=geoId_query
    )
    # user_initial_search_url = "https://www.linkedin.com/jobs/search/?currentJobId=4229231962&distance=25&geoId=103644278&keywords=product%20design%20engineer%20mechanical%20engineering&origin=JOBS_HOME_KEYWORD_HISTORY&refresh=true"


    # How many pages of search results to try (e.g., 1 page = ~25 jobs, 4 pages = ~100 jobs)
    # Be mindful of LinkedIn's limits.
    PAGES_TO_SCRAPE = 2 # Adjust as needed, e.g., 1 for quick test, more for more data

    print(f"Attempting to scrape job summaries (Title, Company, Location, URL) for {PAGES_TO_SCRAPE} page(s)...")
    scraped_jobs = get_linkedin_jobs_fast(user_initial_search_url, num_pages_to_try=PAGES_TO_SCRAPE)

    if scraped_jobs:
        # Remove duplicates based on URL, keeping the first occurrence
        unique_jobs = []
        seen_urls = set()
        for job in scraped_jobs:
            if job['URL'] not in seen_urls:
                unique_jobs.append(job)
                seen_urls.add(job['URL'])
        
        print(f"\nFound {len(scraped_jobs)} jobs in total, {len(unique_jobs)} after removing duplicates.")

        df = pd.DataFrame(unique_jobs)
        
        csv_filename = "linkedin_jobs.csv"
        try:
            df.to_csv(csv_filename, index=False, encoding='utf-8')
            print(f"Successfully saved {len(unique_jobs)} unique jobs to {csv_filename}")
        except Exception as e:
            print(f"Error saving to CSV: {e}")

        print("\n--- Sample of Scraped Data (first 3 unique jobs) ---")
        for i, job in enumerate(unique_jobs[:3]):
            print(f"\nJob {i+1}:")
            print(f"  Title: {job.get('Title')}")
            print(f"  Company: {job.get('Company')}")
            print(f"  Location: {job.get('Location')}")
            print(f"  URL: {job.get('URL')}")
    else:
        print("\nNo job listings were successfully scraped.")

