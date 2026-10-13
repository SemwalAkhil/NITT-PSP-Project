
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
        print("Checking: ",link.strip())
        p.update(t,advance=1)
        html = requests.get(link).text
        soup = BeautifulSoup(html,"html.parser")

        plant_data = []
        tables = soup.find_all("table") 
        for i,table in enumerate(tables):
            plant_data.append([])
            print(i)
            curr_table = []
            for row in table.find_all("tr"):
                print(row)
                datas = [data.text for data in row.find_all("td")]
                if datas != []:
                    plant_data[i].append(datas)  
                else:
                    datas = [data.text for data in row.find_all("tr")]
                    if datas != row.find_all("td"):
                        plant_data[i].append(datas)

        print(plant_data)



        # real world use
        # features 
        # ppt all knowledge
        # system architecture
        # more about cyber and network
        # stick file
        # everything about ppt must be known
        # marks for groups


        break
    
