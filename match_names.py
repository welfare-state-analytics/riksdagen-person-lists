import os, re
import pandas as pd
import numpy as np
from alto import parse_file
import progressbar
import argparse

# Modified versions of gender and add_id, should probably be made general later on
#from pyriksdagen.mp import add_gender, add_id
def add_gender(mp_db, names):
    """
    Based to first names, add gender to an MP dataframe.
    """
    print("Add gender...")
    mp_db["gender"] = None

    name_to_gender = {}
    for i, namerow in names.iterrows():
        name = namerow["name"]
        gender = namerow["gender"]
        if gender == "masculine":
            gender = "man"
        elif gender == "feminine":
            gender = "woman"
        name_to_gender[name] = gender

    for i, row in progressbar.progressbar(list(mp_db.iterrows())):
        first_name = row["name"].split()[0]
        if "-" in first_name:
            first_name = first_name.split("-")[0]
        if first_name in name_to_gender:
            mp_db.loc[i, "gender"] = name_to_gender[first_name]

    return mp_db

import unicodedata
import hashlib
def add_id(mp_db):
    """
    Generate deterministic IDs for mps based on the "name", "party", "district",
    "chamber", "start", and "end" columns of the dataframe.
    """
    print("Add id...")
    columns = mp_db.columns
    columns = ["name", "district", "born", "district", "chamber", "year"]

    mp_db["id"] = None
    print("columns used for generation:", ", ".join(columns))
    for i, row in progressbar.progressbar(list(mp_db.iterrows())):
        name = unicodedata.normalize("NFD", row["name"])
        name = name.encode("ascii", "ignore").decode("utf-8")
        name = name.lower().replace(" ", "_")
        name = name.replace(".", "").replace("(", "").replace(")", "").replace(":", "")
        party = row.get("party")

        pattern = [name]
        for column in columns:
            value = row[column]
            if type(value) != str:
                value = str(value)
            pattern.append(value)

        pattern = "_".join(pattern).replace(" ", "_").lower()

        digest = hashlib.md5(pattern.encode("utf-8")).hexdigest()
        mp_db.loc[i, "id"] = name + "_" + digest[:6]

    return mp_db

def main(args):
    name = "[A-ZÅÖÄÉ][a-zäöåéA-ZÅÄÖ\\-]{2,25}"
    opt_name = "( " + name + ")?"
    born = "f\\. [0-9]{4,4}" # Born eg. f. 1929

    if args.datasource == "personregister":
        folder = "altofiles/"
        pattern = name + ", " + name + opt_name + opt_name + "[\S  ]{0,25}" + born
    elif args.datasource == "statskalender":
        folder = "statscalender/"
        pattern = name + ", " + name + opt_name + opt_name

    print(pattern)
    e = re.compile(pattern)

    print("Test that the regex works:")
    print(e.match("Matsson, Carl Johan sdds f. 1234"))
    print(e.match("Matsson, Carl Johan, f. 1234"))
    print(e.match("Matsson, Carl-Johan, f. 1234"))
    print(e.match("MATSSON, Carl Johan, f. 1234"))
    print(e.match("Matsson, Carl Magnus Isak i dssdd f. 1234"))
    print(e.match("Matsson, CaRl Johan"))
    print(e.match("Matsson"))

    print("Files to be processed:")
    altofiles = os.listdir(folder)
    altofiles = sorted(altofiles)
    altofiles = [f for f in altofiles if f != '.xml']

    ms = {}
    for altofile in progressbar.progressbar(altofiles):
        decade = altofile[3:].split("-")[0]
        fpath = folder + altofile

        # Skip files that are of incorrect format
        try:
            alto = parse_file(fpath)
        except Exception:
            continue

        words = alto.extract_words()
        text = " ".join(words)
        matches = e.finditer(text)
        starts = []
        ends = []
        names = []

        #if matches is None:
        year = int(altofile.split('-')[0][-4:])

        # Match names with regex; anything between two names
        # is also saved as potential metadata
        if matches is not None:
            for match in matches:
                start = match.start()
                end = match.end()
                matched_str = text[start:end]
                starts.append(start)
                ends.append(end)
                names.append(matched_str)

        starts.append(-1)
        inbetweens = zip(ends, starts[1:])
        inbetweens = [text[e:s] for e,s in inbetweens]

        m = {name: description for name, description in zip(names, inbetweens)}

        decade_m = ms.get(decade, {})
        for name, description in m.items():
            if len(name.split()[0]) <= 1:
                name = name[2:]
            decade_m[name] = description
        ms[decade] = decade_m

    #print(ms)
    return ms

def to_df(ms, datasource):
    """
    Convert matched pieces of text into structured metadata
    """
    district_pattern = "[A-ZÅÖÄ][a-zäöå][a-zäöåA-ZÅÖÄ ]{2,35} län"
    district_e = re.compile(district_pattern)

    if datasource == "personregister":
        pattern = "f. [0-9]{4,4}"
    else:
        pattern = "f. [0-9]{2,2}"
    e = re.compile(pattern)


    pattern2 = " [A-ZÅÖÄ][a-zäöå]{2,20},"
    e2 = re.compile(pattern2)

    rows = []

    name = "[A-ZÅÖÄ][a-zäöåA-ZÅÄÖ\\-]{2,25}"
    opt_name = "( " + name + ")?"
    namepattern = name + ", " + name + opt_name + opt_name
    eName = re.compile(namepattern)

    locations = pd.read_csv("metadata/locations.csv")["place"]
    locations = set(locations)

    for decade in ms:
        for name, description in ms[decade].items():
            #if "f. " in description[:40]:
            #print(name)#, description.split("Yttran")[0])

            if datasource == "personregister":
                match = e.search(name)
            else:
                match = e.search(description)
            description = description.replace(" | ", " ")
            description = description.replace("- ", "")
            #print(match)
            #print(name, description)

            namematch = eName.search(name)

            if match is not None and namematch is not None:
                born = int(match.group(0)[3:])
                municipality = None
                district = None
                for m in e2.finditer(description):
                    m = m.group(0).replace(",", "").strip()

                    if m in locations:#m != "Johannesnäs":
                        municipality = m
                        break
                
                for m in district_e.finditer(description):
                    m = m.group(0)
                    district = m

                name = namematch.group(0)
                capitalized_name = name.lower().split()
                capitalized_name = " ".join(["-".join([w.capitalize() for w in wd.split("-")])
                    for wd in capitalized_name])
                chamber = None
                if "LAK" in description:
                    chamber = "ak"
                elif "LFK" in description:
                    chamber = "fk"
                row = [decade, capitalized_name, born, municipality, district, chamber]

                rows.append(row)

    df = pd.DataFrame(rows, columns=["decade", "name", "born", "municipality", "district", "chamber"])
    
    if datasource == "statskalender":
        df["year"] = df["decade"].str[-4:].astype(int)
        # Check whether born in the 1800s or 1900s
        df["born"] = np.where(df["born"] + 1900 >= df["year"], df["born"] + 1800, df["born"] + 1900)

        def fixname(n):
            if ", " in n:
                s = n.split(", ")
                return ", ".join(s[1:]) + " " + s[0]
            else:
                return n

        df["name"] = df["name"].apply(lambda n: fixname(n))

    return df

if __name__ == '__main__':

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--datasource", type=str, choices=["personregister", "statskalender"])
    parser.add_argument("--outpath", type=str, default="metadata/mps.csv")
    args = parser.parse_args()

    ms = main(args)
    df = to_df(ms, args.datasource)
    # Added some cleaning and id
    df["name"] = list(map(lambda x: x.replace(',', ''), df["name"]))
    df = add_id(df)

    print(df)

    print('Ids are unique is: ', len(df) == len(set(df["id"])))

    df.to_csv(args.outpath, index=False)

