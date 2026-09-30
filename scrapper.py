
from bs4 import BeautifulSoup
import requests

DRAVYA = "https://dravya.ccras.org.in/all_plants"
html = requests.get(DRAVYA).text
soup = BeautifulSoup(html,"html.parser")
links = []
for i in soup.find_all("a"):
    if i.text.strip().lower() == "view":
        links.append(i["href"])
        print(i["href"])
    else:
        for j in i.children:
            print("> ",j)
        print("----------------------")
    