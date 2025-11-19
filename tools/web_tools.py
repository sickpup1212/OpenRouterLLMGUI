"""Web scraping tools for extracting content from websites."""

import json
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from tools.registry import tool_registry


@tool_registry.register(
    description="Fetches a URL and extracts the main text content, like headlines and paragraphs",
    requires_confirmation=False
)
def scrape_site(url):
    """
    Fetches a URL and extracts the main text content, like headlines and paragraphs.
    Args:
        url (str): The URL of the webpage to scrape.
    Returns:
        str: A string containing the extracted text, or an error message.
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        return f"Error fetching URL: {e}"
    soup = BeautifulSoup(response.text, 'lxml')
    for tag in soup(['script', 'style', 'nav', 'footer', 'aside', 'header', 'form']):
        tag.decompose()
    main_content = soup.find('main') or soup.find('article') or soup.find('div', class_=lambda c: c and 'content' in c.lower()) or soup.body
    if not main_content:
        return "Could not find main content area."
    text_parts = []
    for element in main_content.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'li', 'blockquote']):
        text = element.get_text(strip=True)
        if text:
            text_parts.append(text)
    full_text = "\n\n".join(text_parts)
    return full_text


@tool_registry.register(
    description="Fetches a URL and extracts all links with their text content",
    requires_confirmation=False
)
def scrape_site_for_links(url, start=20, end=40):
    """
    Fetches a URL and extracts all links with their text content.
    Args:
        url (str): The URL of the webpage to scrape.
        start (int): Starting index for link list slice.
        end (int): Ending index for link list slice.
    Returns:
        str: A JSON string containing {link_text: link_href} pairs, or an error message.
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        return f"Error fetching URL: {e}"
    soup = BeautifulSoup(response.text, 'lxml')
    for tag in soup(['script', 'style', 'nav', 'footer', 'aside', 'header', 'form']):
        tag.decompose()
    links = soup.find_all('a', href=True)
    link_dicts = []
    for link in links:
        text = link.get_text(strip=True)
        href = link['href']
        if text and href:
            if href.startswith('/'):
                href = urljoin(url, href)
            link_dicts.append({text: href})
    return json.dumps(link_dicts[start:end])
