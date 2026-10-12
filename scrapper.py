
from bs4 import BeautifulSoup
import requests
import re
DRAVYA = "https://dravya.ccras.org.in/all_plants"
html = requests.get(DRAVYA).text
soup = BeautifulSoup(html,"html.parser")
links = set()
curr_page = 1
while True:
    next_page = None
    for page_link in soup.find_all(r"\?page="):
        if int(page_link.text) == curr_page + 1:
            next_page = DRAVYA + page_link["href"]
    for i in soup.find_all(href=re.compile(r"/plant/")):
        # print(i["href"])
        links.add(i["href"])
    if next_page == None:
        break
    else:
        html = requests.get(next_page).text
        soup = BeautifulSoup(html,"html.parser")
        curr_page += 1
print("\n".join(links))
