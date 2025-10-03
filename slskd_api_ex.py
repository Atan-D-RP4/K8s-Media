from dotenv import load_dotenv
import slskd_api

import os

load_dotenv()

host = "http://localhost:5030/"
api_key = os.environ.get("SLSKD_API_KEY")
if api_key is None:
    raise ValueError("SLSKD_API_KEY environment variable not set")

slskd = slskd_api.SlskdClient(host, api_key)

app_status = slskd.application.state()
# available_rooms = slskd.rooms.get_all()
all_searchs = slskd.searches.get_all()

print("App status:", app_status, "\n")
# print("Available rooms:", available_rooms)
# print("All searches: \n", all_searchs)

# print(all_searchs[0])
# for search in all_searchs:
#     text = search["searchText"]
#     state = search["state"]
#     file_count = search["fileCount"]
#     id = search["id"]
#     if "Completed" not in state:
#         search_status = slskd.searches.state(id)
#         print(
#             f"(ID: {id}) - {state} ({search_status}) - Search '{text}' - Files Found: {file_count}"
#         )
#     else:
#         print(f"(ID: {id}) - {state} - Search '{text}' - Files Found: {file_count}")

# responses = slskd.searches.state(all_searchs[0]["id"], True)["responses"]

# for response in responses:
#     print(response)

print()
print()

query = "Imagine Dragons Believer"
search = None
for curr_search in all_searchs:
    if curr_search["searchText"].lower() == query.lower():
        print(curr_search)
        search = curr_search
        break
if search is None:
    new_search = slskd.searches.search_text(query)
    print(new_search)
    search = new_search

print("Search:", search.get("id"))
for response in slskd.searches.search_responses(search.get("id")):
    print(response)
