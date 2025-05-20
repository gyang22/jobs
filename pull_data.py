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
    # Replace multiple newlines with a single space (or a single newline if preferred)
    text = re.sub(r'\s*\n\s*', '\n', text.strip())
    # Replace multiple spaces with a single space
    text = re.sub(r'[ \t]+', ' ', text)
    return text.strip()

def get_linkedin_jobs(search_url, num_pages_to_try=1):
    all_jobs_data = []
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive'
    }
    base_url_for_pagination = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
    try:
        params_from_user_url = dict(qc.split("=") for qc in search_url.split("?")[1].split("&"))
        keywords = params_from_user_url.get('keywords', 'product%20design%20engineer%20mechanical%20engineering')
        geoId = params_from_user_url.get('geoId', '103644278')
    except Exception:
        print("Could not parse keywords/geoId from initial URL for pagination. Using defaults.")
        keywords = "product%20design%20engineer%20mechanical%20engineering"
        geoId = "103644278"

    for page_num in range(num_pages_to_try):
        start_index = page_num * 25
        if page_num == 0:
            current_url = search_url
            print(f"Fetching initial URL: {current_url}")
        else:
            current_url = f"{base_url_for_pagination}?keywords={keywords}&location=&geoId={geoId}&start={start_index}"
            print(f"Fetching paginated URL: {current_url}")

        try:
            response = requests.get(current_url, headers=headers, timeout=15) # Increased timeout
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            job_cards = []
            # Try more specific selectors first
            if page_num == 0 and "linkedin.com/jobs/search/" in search_url:
                 job_cards = soup.find_all('div', class_='base-search-card')
            if not job_cards: # If above fails or for API calls
                job_cards = soup.find_all('li', class_='job-result-card') # Common for guest API
            if not job_cards: # Fallback
                job_cards = soup.find_all('li')


            print(f"Found {len(job_cards)} potential job cards on page {page_num + 1}.")
            if not job_cards and page_num > 0:
                print(f"No job cards found using guest API structure on page {page_num + 1}.")

            page_jobs = []
            for card in job_cards:
                job_title_element = card.find('h3', class_=['base-search-card__title', 'job-result-card__title'])
                job_company_element = card.find('h4', class_=['base-search-card__subtitle', 'job-result-card__subtitle'])
                job_location_element = card.find('span', class_=['job-search-card__location', 'job-result-card__location'])
                job_link_element = card.find('a', class_=['base-card__full-link', 'job-result-card__card-link'])
                if not job_link_element: # More general fallback for a link within the card
                     job_link_element = card.find('a', href=True)


                job_title = clean_text_for_csv(job_title_element.text) if job_title_element else None
                company_name = clean_text_for_csv(job_company_element.text) if job_company_element else None
                location = clean_text_for_csv(job_location_element.text) if job_location_element else None
                job_url = job_link_element['href'] if job_link_element else None
                
                # Ensure URL is absolute
                if job_url and not job_url.startswith('http'):
                    job_url = f"https://www.linkedin.com{job_url}" if job_url.startswith('/') else f"https://www.linkedin.com/jobs/view/{job_url}"


                if job_title and company_name:
                    job_data = {
                        'Title': job_title,
                        'Company': company_name,
                        'Location': location,
                        'URL': job_url,
                        'Description_Preview': '' # Will be filled later
                    }
                    page_jobs.append(job_data)
            
            if not page_jobs and len(job_cards) > 0:
                print(f"Could not extract structured job data despite finding {len(job_cards)} cards. Selectors might be outdated.")

            all_jobs_data.extend(page_jobs)
            time.sleep(random.uniform(3, 7)) # Increased delay
            if not page_jobs and page_num > 0 :
                 print(f"Stopping pagination attempt as page {page_num+1} yielded no structured jobs.")
                 break
            if not job_cards and page_num > 0:
                print(f"Stopping pagination attempt as page {page_num+1} yielded no job cards via API guess.")
                break
        except requests.exceptions.RequestException as e:
            print(f"Request failed for {current_url}: {e}")
            break
        except Exception as e:
            print(f"An error occurred while processing page {page_num + 1}: {e}")
            continue
    return all_jobs_data

def get_job_description(job_url, headers):
    if not job_url:
        return "No URL provided"
    try:
        response = requests.get(job_url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        description_container = soup.find('div', class_='show-more-less-html__markup')
        if not description_container:
            description_container = soup.find('section', class_='description') # Common class
        if not description_container: # More generic class often containing description
            description_container = soup.find('div', class_='job-view-layout__description')
        if not description_container:
             description_container = soup.find('article') # Fallback to article tag
        if not description_container: # Fallback to a more generic content area
            description_container = soup.find('div', class_='decorated-job-posting__details')


        if description_container:
            # Extract text and join paragraphs/list items with newlines
            text_elements = description_container.find_all(['p', 'li', 'ul'])
            description_parts = []
            if text_elements:
                for element in text_elements:
                    if element.name == 'ul':
                        for li in element.find_all('li', recursive=False): # Only direct children
                            description_parts.append(f"- {clean_text_for_csv(li.get_text())}")
                    else:
                        description_parts.append(clean_text_for_csv(element.get_text()))
                full_description = "\n".join(description_parts)
            else: # If no p or li, get all text from the container
                full_description = clean_text_for_csv(description_container.get_text(separator='\n'))
            return full_description
        return "Description not found with primary selectors."
    except requests.exceptions.RequestException as e:
        print(f"Failed to fetch job description from {job_url}: {e}")
        return f"Error fetching description: {e}"
    except Exception as e:
        print(f"An error occurred while parsing job description from {job_url}: {e}")
        return f"Error parsing description: {e}"

if __name__ == "__main__":
    linkedin_search_url = "https://www.linkedin.com/jobs/search/?currentJobId=4229231962&distance=25&geoId=103644278&keywords=product%20design%20engineer%20mechanical%20engineering&origin=JOBS_HOME_KEYWORD_HISTORY&refresh=true"
    # For a broader search, a simpler URL is often better:
    # linkedin_search_url = "https://www.linkedin.com/jobs/search/?keywords=product%20design%20engineer&location=United%20States&geoId=103644278&f_TPR=r86400" # Last 24 hours

    print("Attempting to scrape job listings...")
    # Limit pages for example, increase for more data
    scraped_jobs_summary = get_linkedin_jobs(linkedin_search_url, num_pages_to_try=1) 

    detailed_jobs_data = []

    if scraped_jobs_summary:
        print(f"\n--- Fetching descriptions for {len(scraped_jobs_summary)} jobs ---")
        headers_for_desc = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36'
        }
        for i, job_summary in enumerate(scraped_jobs_summary):
            print(f"Processing job {i+1}/{len(scraped_jobs_summary)}: {job_summary.get('Title')} at {job_summary.get('Company')}")
            if job_summary.get('URL'):
                time.sleep(random.uniform(2, 5)) # Delay before fetching individual job page
                description = get_job_description(job_summary['URL'], headers_for_desc)
                job_summary['Description_Preview'] = description[:500] + "..." if description and len(description) > 500 else description # Store a preview or full description
            detailed_jobs_data.append(job_summary)
        
        # Create a DataFrame
        df = pd.DataFrame(detailed_jobs_data)
        
        # Save to CSV
        csv_filename = "linkedin_jobs.csv"
        try:
            df.to_csv(csv_filename, index=False, encoding='utf-8')
            print(f"\nSuccessfully saved {len(detailed_jobs_data)} jobs to {csv_filename}")
        except Exception as e:
            print(f"Error saving to CSV: {e}")

        # Print a sample
        print("\n--- Sample of Scraped Data (first 3 jobs) ---")
        for i, job in enumerate(detailed_jobs_data[:3]):
            print(f"\nJob {i+1}:")
            print(f"  Title: {job.get('Title')}")
            print(f"  Company: {job.get('Company')}")
            print(f"  Location: {job.get('Location')}")
            print(f"  URL: {job.get('URL')}")
            print(f"  Description Preview: {job.get('Description_Preview', '')[:200]}...")
    else:
        print("\nNo job listings were successfully scraped.")

