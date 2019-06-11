import sys
import os

import pandas as pd

filenames = sys.argv[1:]


def read_summary(fn):
    df = pd.read_csv(fn, sep='\t')
    sample = os.path.basename(fn).split('_')[0]
    df = df.iloc[:,:2]
    df = df.set_index("# classification")
    df.index.name = "classification"
    return sample,  df.iloc[:,:1]


if __name__ == '__main__':
    
    samples, otu_names = [], set()
    data = []
    for fn in sys.argv[1:]:
        sample, counts = read_summary(fn)
        samples.append(sample)
        data.append(counts)
        otu_names.update(list(counts.index))
    X = pd.concat(data, axis=1)
    X.columns = samples
    X = X.fillna(0)
    X.to_csv(sys.stdout, sep="\t")
    

    
