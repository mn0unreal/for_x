# twitter(x) followers
<code>./run_twitter.sh </code>
<img width="1442" height="836" alt="image" src="https://github.com/user-attachments/assets/67fe2cda-d5da-4b7f-9cfc-b8a899a8b6ca" />
# result
<img width="1294" height="844" alt="image" src="https://github.com/user-attachments/assets/c540b6ca-6bf8-4763-856c-b4aa9c2b0b5d" />

# for_x

Twitter follower counter (MOMAH Edition)

Overview
- A small Selenium-based tool that reads a list of X/Twitter account URLs or handles and writes follower counts to an Excel file.
- Main script: [TWFollowers.prompt.py](TWFollowers.prompt.py)

Requirements
- Ubuntu dev container (this workspace)
- Python 3.8+ and these Python packages:
  - selenium
  - webdriver-manager
  - pandas
  - tqdm
  - openpyxl (for Excel output)
- Chrome/Chromium available in the container (webdriver-manager will install the driver)

Install dependencies
```sh
pip install selenium webdriver-manager pandas tqdm openpyxl
```
for run command
```./run_twitter.sh```
