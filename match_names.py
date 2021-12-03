import os, re
import pandas as pd
from alto import parse_file
import progressbar
import argparse

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
    print(altofiles[:25])

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

    return ms

def to_df(ms):
    """
    Convert matched pieces of text into structured metadata
    """
    district_pattern = "[A-ZÅÖÄ][a-zäöå][a-zäöåA-ZÅÖÄ ]{2,35} län"
    district_e = re.compile(district_pattern)

    pattern = "f. [0-9]{4,4}"
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

            match = e.search(name)
            description = description.replace(" | ", " ")
            description = description.replace("- ", "")
            #print(match)


            namematch = eName.search(name)

            if match is not None and namematch is not None:
                year = int(match.group(0)[3:])
                municipality = None
                district = None
                for m in e2.finditer(description):
                    m = m.group(0).replace(",", "").strip()

                    if m in locations:#m != "Johannesnäs":
                        municipality = m
                        break
                if "hansson" in name.lower() and "Önnarp" in description:
                    print(municipality, description)
                
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
                row = [decade, capitalized_name, year, municipality, district, chamber]

                rows.append(row)

    df = pd.DataFrame(rows, columns=["decade", "name", "year", "municipality", "district", "chamber"])
    return df

if __name__ == '__main__':

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--datasource", type=Datasource, choices=["personregister", "statskalender"])
    parser.add_argument("--outpath", type=str, default="metadata/mps.csv")
    args = parser.parse_args()

    ms = main(args)
    df = to_df(ms)

    print(df)

    df.to_csv(args.outpath, index=False)

