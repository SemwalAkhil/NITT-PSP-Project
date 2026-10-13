
from bs4 import BeautifulSoup
import requests
import re
from rich.progress import Progress
 
DRAVYA = "https://dravya.ccras.org.in/all_plants"
html:str = requests.get(DRAVYA).text
soup:BeautifulSoup = BeautifulSoup(html,"html.parser")
links:set[str] = set()
curr_page:int = 1

with Progress() as p:
    t = p.add_task("Fetching plant links: ", total=None)
    while True:
        next_page:str|None = None
        for page_link in soup.find_all(href=re.compile(r"\?page=")):
            if (int(page_link.text.strip()) if page_link.text.strip().isdecimal() else -1) == curr_page + 1:
                next_page = DRAVYA + page_link["href"]
        for i in soup.find_all(href=re.compile(r"/plant/")):
            links.add(i["href"])
        if next_page == None:
            break
        else:
            html = requests.get(next_page).text
            soup = BeautifulSoup(html,"html.parser")
            curr_page += 1

# print(len(links))
# print("\n".join(links))

with Progress() as p:
    t = p.add_task("Fetching Tables: ",total=len(links))
    for link in links:
        print("Checking: ",link)
        p.update(t,advance=1)
        html = requests.get(link).text
        soup = BeautifulSoup(html,"html.parser")

        plant_data = []
        tables = soup.find_all("table") 
        for i,table in enumerate(tables):
            curr_table = []
            # table_head = table.find("thead")
            # row = table_head.find("tr")
            # heads = row.find_all("th")
            # for head in heads:
            #     plant_data[i] = {head:[]}
            # table_body = table.find("tbody")
            # rows = table_body.find_all("tr")
            # for row in rows:
            #     datas = row.find_all("td")
            #     for data in datas:
            #         plant_data[i]
            for row in table.find_all("tr"):
                datas = row.find_all("th")
                if datas != []:
                    plant_data[i].append  
                if row.find_all("th") != []:

        print(tables)



        # real world use
        # features 
        # ppt all knowledge
        # system architecture
        # more about cyber and network
        # stick file
        # everything about ppt must be known
        # marks for groups


        break
    
