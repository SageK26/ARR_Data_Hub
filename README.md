# ARR_Data_Hub
Extracting ARR initial and continuing losses using ARR Data Hub 2026 v1

Step-by-step guide for extracting rainfall loss data from your ARR Data Hub 2026 text export:

Step 1: Download your data
Go to the ARR Data Hub, download your results as the 2026 version text file, and save it with the exact name input.txt.

Step 2: Run the script
You have two options, choose whichever suits you.

Option A: Terminal
Open a terminal in the folder where input.txt and tuflow_extract_txt.py are both saved, then run:
python tuflow_extract_txt.py input.txt

Option B: Jupyter Notebook
In a notebook cell, run:

from tuflow_extract_txt import run
run("input.txt")

Step 3: Choose where the output file is saved (optional)
By default, the script saves the results to a file called rainfall_losses.trd in the same folder.

If you want to choose a different name or location for this file, add the trd_path option:

from tuflow_extract_txt import run
run("input.txt", trd_path="my_losses.trd")

That's it
Once run, the script prints the extracted Continuing Loss and Initial Loss values to the screen, confirms where the .trd file was saved, and lists any AEP and duration combinations using the preburst temporal pattern instead of a fixed loss value.
