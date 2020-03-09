#!/usr/bin/env python

import copy
import argparse
import os
from os.path import join, abspath, exists, basename
import sys
from tempfile import mkdtemp
import shutil
import subprocess
import multiprocessing as mp
import glob
import itertools
import collections

import qiime2
from qiime2 import Artifact, Metadata
from qiime2.plugins import metadata, feature_table, alignment, phylogeny, diversity, feature_classifier, taxa, dada2, demux

import pandas as pd

__doc__ = "Analysis of microbiome fastq files with QIIME2"
__version__ = '0.1'

PRIMERS = {}
_qiaseq_primers = {}
_qiaseq_primers["V1V2"] = "AGRGTTTGATYMTGGCTC-CTGCTGCCTYCCGTA"  # 8F - 338R
_qiaseq_primers["V2V3"] = "GGCGNACGGGTGAGTAA-WTTACCGCGGCTGCTGG"
_qiaseq_primers["V3V4"] = "CCTACGGGNGGCWGCAG-GACTACHVGGGTATCTAATCC"  # 341F - 805R
_qiaseq_primers["V4V5"] = "GTGYCAGCMGCCGCGGTAA-CCGYCAATTYMTTTRAGTTT"
_qiaseq_primers["V5V7"] = "GGATTAGATACCCBRGTAGTC-ACGTCRTCCCCDCCTTCCTC"
_qiaseq_primers["V7V9"] = "YAACGAGCGMRACCC-TACGGYTACCTTGTTAYGACTT"
_qiaseq_primers["ITS1"] = "CTTGGTCATTTAGAGGAAGTAA-GCTGCGTTCTTCATCGATGC"  # ITS1F - ITS2R
_qiaseq_primers["ITS2"] = "GTGARTCATCGARTCTTTGAA-CTBTTVCCKCTTCACTCG"  # ITS86F - ITS4_KYO3
_ilmn_v4_primers = {}
_ilmn_v4_primers["V4"] = "GTGYCAGCMGCCGCGGTAA-GGACTACNVGGGTWTCTAAT"
PRIMERS["qiaseq"] = _qiaseq_primers
PRIMERS["ilmn_v4"] = _ilmn_v4_primers
PRIMERS["QIAseq_16S_ITS_Region_Panels"] = _qiaseq_primers
PRIMERS["16S_Metagenomic_Sequencing_Library_Prep"] = _ilmn_v4_primers

def get_parser():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", help="input fastq files", nargs="+")
    parser.add_argument("--output-dir", help="output directory", required=True)
    parser.add_argument("--sample-info", help="sample metadata", required=True)
    parser.add_argument("--libprep", help="library preparation kit", choices=list(PRIMERS.keys()), required=True)
    parser.add_argument("--regions", help="comma separated list of variable regions", required=False)
    parser.add_argument("--taxonomy-db", help="reference database", choices=['silva', 'greengenes', 'universal'], required=True)
    parser.add_argument("--classifier-dir", help="path to prebuild classifiers", required=True)
    parser.add_argument("--filter-region-count", help="minimum number of reads within a region", type=int, default=500)
    parser.add_argument("--min-confidence", help="minimum accepted confidence for feature classifier", type=float, default=0.8)
    parser.add_argument("--build-tree", help="output phylogenetic tree", action="store_true")
    parser.add_argument("--threads", help="number of threads", type=int, default=1)
    return parser


def cutadapt_worker(fname, regions, primers):
    """Split fastq files into regions by matching 5 prime ends with conserved region primer sequences.

    This function requires cutadapt installed (tested with cutadapt 2.8)
    """
    sample = basename(fname).split('_R1.fastq')[0]
    for region, seq in primers.items():
        fwd, rev = seq.split('-')
        if exists('{}_unknown_R1.fastq'.format(sample)):
            fname = '{}_unknown_R1.fastq'.format(sample)
            cp_cmd = 'mv -f {} input_{}'.format(fname, fname)
            subprocess.check_call(cp_cmd, shell=True)
            cp_cmd = 'mv -f {} input_{}'.format(fname.replace('R1.fastq', 'R2.fastq'), fname.replace('R1.fastq', 'R2.fastq'))
            subprocess.check_call(cp_cmd, shell=True)
            cmd = """cutadapt -g {region}={fwd_primer} -G {region}={rev_primer} --pair-adapters --no-indels -e 0.1 --untrimmed-output {unknown_r1} --untrimmed-paired-output {unknown_r2} --suffix ':region={{name}}' -o {sample}_{{name}}_R1.fastq -p {sample}_{{name}}_R2.fastq {r1} {r2} >> log/{sample}_region_demultiplex.log"""
        cmd = cmd.format(
            sample=sample,
            unknown_r1='{}_unknown_R1.fastq'.format(sample),
            unknown_r2='{}_unknown_R2.fastq'.format(sample),
            region=seq,
            fwd_primer=r['primer'],
            rev_primer=reverse.loc[i, 'primer'],
            r1=('input_' + fname) if 'unknown_R1.fastq' in fname else fname,
            r2=('input_' + fname.replace('R1.fastq', 'R2.fastq'))
            if 'unknown_R1.fastq' in fname
            else fname.replace('R1.fastq', 'R2.fastq'),
        )
        subprocess.check_call(cmd, shell=True)

    rm_cmd = 'rm input_{}_*fastq'.format(sample)
    subprocess.check_call(rm_cmd, shell=True)


def seqkit_worker(fname, region):
    """split fastq files into regions by matching fastq header
    
    Region header is identified by region=, e.g region=V1V2.
    This function requires seqkit installed (tested with version 0.12)
    
    """
    sample = basename(fname).split('_R1.fastq')[0]

    cmd = 'seqkit grep -n -r -p region={} {} -o {}_{}_R1.fastq'.format(region, fname, sample, region)
    subprocess.check_call(cmd, shell=True)
    fname = fname.replace('_R1.fastq', '_R2.fastq')
    cmd = 'seqkit grep -n -r -p region={} {} -o {}_{}_R2.fastq'.format(region, fname, sample, region)
    subprocess.check_call(cmd, shell=True)
    print(cmd)

    # clean up empty files
    # subprocess.check_call("""for file in *.fastq; do if [[ ! -s $file ]]; then rm $file; fi; done""", shell=True)


def pandas_manifest(R1):
    """Create a qiime2 manifest format pandas dataframe from a list of fwd fastq reads.
    """
    header = ['sample-id', 'forward-absolute-filepath', 'reverse-absolute-filepath']
    rows = []
    for fn in R1:
        if os.stat(fn).st_size > 0:
            sample_id = basename(fn).split('_R1.fastq')[0]
            fn2 = fn.replace('_R1', '_R2')
            assert exists(fn2)
            rows.append([sample_id, fn, fn2])
    if len(rows) > 0:
        df = pd.DataFrame(rows, columns=header)
        return df


def import_data_worker(manifest_fn):
    return Artifact.import_data('SampleData[PairedEndSequencesWithQuality]', manifest_fn,
                                view_type='PairedEndFastqManifestPhred33V2')


def demultiplex_manifests(fastq_files, regions=None, libprep='qiaseq', split_on_header=True, threads=4):
    """Demultiplex fastq files into variable region origins.
    """
    if regions == None and libprep is not None:
        regions = list(PRIMERS[libprep].keys())
    r1 = [abspath(i) for i in fastq_files if '_R1.fastq' in i]
    rundir = mkdtemp() #run in a tmpdir
    cwd = os.path.abspath(os.curdir)
    os.chdir(rundir)
    with mp.Pool(threads) as pool:
        if split_on_header:
            args_iter = itertools.product(r1, regions)
            pool.starmap(seqkit_worker, args_iter)
        else:
            pool.map(cutadapt_worker, r1, PRIMERS[libprep])

    manifest_filenames = {}
    for r in regions:
        R1 = glob.glob(join(rundir, '*_{}_R1.fastq'.format(r)))
        df = pandas_manifest(R1)
        manifest_fn = r + '_manifest.csv'
        if df is not None:
            df.to_csv(manifest_fn, index=False, sep='\t')
            manifest_filenames[r] = manifest_fn

    adata = {}
    for r, fn in manifest_filenames.items():
        adata[r] = import_data_worker(fn)

    # clean up tmpdir
    os.chdir(cwd)
    shutil.rmtree(rundir)
    return adata


def sequence_counts(adata, min_count=500):
    """Summarize read count for each sample.
    """
    counts = {}
    merged_counts = collections.defaultdict(int)
    for k, v in adata.items():
        s = demux.visualizers.summarize(v)
        fn = glob.glob(str(s.visualization._archiver.path) + '/*/data/per-sample-fastq-counts.csv')[0]
        df = pd.read_csv(fn)
        count = df['Sequence count'].median()
        if count > min_count:
            counts[k] = df
            for name, row in df.iterrows():
                merged_counts[row['Sample name']] += int(row['Sequence count'])
    return counts, merged_counts


def denoise_dada2(adata, trunc_len_f=0, trunc_len_r=0, trim_left_f=0, trim_left_r=0, max_ee_f=2.0, max_ee_r=2.0, trunc_q=2,
                  min_fold_parent_over_abundance=1.0, threads=4):
    """
    """
    tables, seqs, stats = {}, {}, {}
    for region, data in adata.items():
        try:
            res = dada2.methods.denoise_paired(data, trunc_len_f=trunc_len_f, trunc_len_r=trunc_len_r,
                                               trim_left_f=trim_left_f, trim_left_r=trim_left_r,
                                               max_ee_f=max_ee_f, max_ee_r=max_ee_r,
                                               min_fold_parent_over_abundance=min_fold_parent_over_abundance,
                                               n_threads=threads, n_reads_learn=1000000, hashed_feature_ids=True)
            tables[region], seqs[region], stats[region]  = res
        except Exception as inst:
            print('skipping ' + region)
            print(type(inst))
            print(inst.args)
            print(inst)

    return tables, seqs, stats


def dada2_summary(tables, sequences, stats):
    summary = {}
    for r in tables.keys():
        summary[r] = {}
        summary[r]['sequence'] = feature_table.visualizers.tabulate_seqs(sequences[r])
        summary[r]['table'] = feature_table.visualizers.summarize(tables[r])
        summary[r]['stats'] = metadata.visualizers.tabulate(stats[r].view(qiime2.Metadata))

    return summary


def taxonomy_classify(sequences, classifier_dir, primers, level='99', threads=4):
    taxas = {}
    for region, repseq in sequences.items():
        clf_name = '{}_{}'.format(level, primers[region])
        clf_pth = join(classifier_dir, clf_name)
        print('loading classifier: {}'.format(clf_pth))
        classifier = qiime2.Artifact.import_data('TaxonomicClassifier', clf_pth)
        taxas[region] = feature_classifier.methods.classify_sklearn(reads=repseq, classifier=classifier, n_jobs=threads, reads_per_batch=20000)
    return taxas


def region_sample_info(samples, region):
    samples_region = copy.deepcopy(samples)
    samples_region._dataframe.index = samples._dataframe.index + '_' + region
    samples_region._ids = tuple(samples._dataframe.index + '_' + region)
    return samples_region


def taxonomy_summary(taxas, sequences, samples):
    summary = {}
    for r in taxas.keys():
        samples_region = region_sample_info(samples, r)
        summary[r] = {}
        summary[r]['taxa'] = metadata.visualizers.tabulate(taxas[r].classification.view(qiime2.Metadata))
        summary[r]['taxa_bar'] = taxa.visualizers.barplot(sequences[r], taxas[r].classification, samples_region)
    return summary


def merge_data(tables, taxas, sequences, samples):
    taxa_list = []
    table_list = []
    seq_list = []
    meta_region = []
    # ensure same ordering of dicts
    for r in taxas.keys():
        taxa_list.append(taxas[r].classification)
        df = tables[r].view(pd.DataFrame)
        df.index = df.index.str.replace('_{}'.format(r), '')
        meta_region.extend([r] * df.shape[1])
        table = Artifact.import_data('FeatureTable[Frequency]', df)
        table_list.append(table)
        seq_list.append(sequences[r])
    merged_taxa = feature_table.methods.merge_taxa(taxa_list)
    merged_seq = feature_table.methods.merge_seqs(seq_list)
    merged_table = feature_table.methods.merge(
        table_list, overlap_method='error_on_overlapping_feature'
    )

    #
    meta = pd.DataFrame(meta_region)
    meta.index = merged_table.merged_table.view(pd.DataFrame).columns
    meta.index.name = 'feature-id'
    meta.columns = ['region']
    meta = Metadata(meta)


    return merged_table, merged_taxa, merged_seq, meta


def filter_features(table, taxonomy, sequence, db, min_confidence):
    """Filter out features without phylum classification, low confidence or matching mitochondria/chloroplast.
    """
    T = table.merged_table.view(pd.DataFrame)  
    X = taxonomy.merged_data.view(pd.DataFrame)
    S = sequence.merged_data.view(pd.Series)

    if db == 'silva':
        has_phylum = X.Taxon.str.contains('D_1__')
    elif db == 'greengenes':
        has_phylum = X.Taxon.str.contains('p__')
    else:
        print('ERROR: db not valid!')
        sys.exit(-1)
        
    keep = (X.Confidence.astype('d') > min_confidence) & \
           (X.Taxon.str.contains('chloroplast')==False) & \
           (X.Taxon.str.contains('mitochondria')==False) & \
           has_phylum
    
    table = Artifact.import_data('FeatureTable[Frequency]', T.loc[:,keep] )
    taxonomy = Artifact.import_data('FeatureData[Taxonomy]', X[keep])
    sequence = Artifact.import_data('FeatureData[Sequence]', S[keep])
    return table, taxonomy, sequence

def summary_data(table, taxonomy, sequence, samples):
    # summaries
    summary = {}
    summary['taxa'] = metadata.visualizers.tabulate(table.view(qiime2.Metadata))
    summary['taxa_bar'] = taxa.visualizers.barplot(table, taxonomy, samples)
    summary['table'] = feature_table.visualizers.summarize(table)
    summary['sequence'] = feature_table.visualizers.tabulate_seqs(sequence)
    return summary


def build_phylogenetic_tree(sequence, threads):
    mafft_alignment = alignment.methods.mafft(sequence, n_threads=threads)
    masked_mafft_alignment = alignment.methods.mask(mafft_alignment.alignment)
    unrooted_tree = phylogeny.methods.fasttree(masked_mafft_alignment.masked_alignment, n_threads=threads)
    rooted_tree = phylogeny.methods.midpoint_root(unrooted_tree.tree)
    return rooted_tree


def create_biom(table, taxonomy, sequence, features_meta=None, samples_meta=None):
    import biom
    from datetime import datetime
    T = table.view(biom.Table)
    T.type = 'OTU table'
    T.create_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    FEATURES = taxonomy.view(pd.DataFrame)
    FEATURES.columns = ['taxonomy', 'confidence']
    tax_table = FEATURES.taxonomy.str.split(';', expand=True)
    
    md_taxa = FEATURES.to_dict(orient='index')
    for k, v in md_taxa.items():
        v['taxonomy'] = list(tax_table.loc[k,:])
        
    T.add_metadata(md_taxa, axis='observation')
    if samples_meta:
        SAMPLES = samples_meta.to_dataframe()
        # be gentle with json parsers and rm nan
        SAMPLES,fillna(value='', inplace=True)
        md_samples = SAMPLES.to_dict(orient='index')
        T.add_metadata(md_samples, axis='sample')
    if features_meta:
        md_features = features_meta.to_dataframe().to_dict(orient='index')
        T.add_metadata(md_features, axis='observation')
    return T


def calc_diversity_region(tables, sample_meta=None, threads=8, metrics=['observed_otus', 'shannon'], max_depth=None):
    diversity_res = {}
    for region, data in tables.items():
        metadata = region_sample_info(samples, region)
        # res = diversity.actions.core_metrics(data, sampling_depth=sampling_depth, metadata=metadata, with_replacement=True, n_jobs=threads)
        if max_depth is None:
            max_depth = int(data.view(pd.DataFrame).sum(1).median() / 2.0)
            print(max_depth)
        res = diversity.actions.alpha_rarefaction(data, max_depth=max_depth, metrics=set(metrics),
                                                  metadata=metadata, steps=20, iterations=30)
        diversity_res[region] = res
    return diversity_res


def write_data(table, taxonomy, sequence, adata, biom_table, denoise_viz_region, taxa_viz_region, summary):
    os.makedirs(args.output_dir, exist_ok=True)

    table.save(join(args.output_dir, 'table'))
    taxonomy.save(join(args.output_dir, 'taxonomy'))
    sequence.save(join(args.output_dir, 'sequence'))
    

    with open(join(args.output_dir, 'table.biom'), 'w') as fh:
        biom_table.to_json('GCF qiime2 pipeline', fh)
    with open(join(args.output_dir, 'table.tsv'), 'w') as fh:
        fh.write(biom_table.to_tsv())
        
    samples = biom_table.metadata_to_dataframe('sample')
    if samples is not None:
        with open(join(args.output_dir, 'sample_info.tsv'), 'w') as fh:
            samples.index.name = 'Sample_ID'
            samples.reset_index(inplace=True)
            samples.to_csv(fh, sep='\t', index=False)
    features = biom_table.metadata_to_dataframe('observation')
    if features is not None:
        with open(join(args.output_dir, 'feature_info.tsv'), 'w') as fh:
            if features.index.name is None:
                features.index.name = 'Feature_ID'
            features.reset_index(inplace=True)
            features.to_csv(fh, sep='\t', index=False)

    for region, data in adata.items():
        os.makedirs(join(args.output_dir, 'regions', region), exist_ok=True)
        data.save(join(args.output_dir, 'regions', region, 'demultiplexed.qza'))

    for region, data in denoise_viz_region.items():
        for name, viz in data.items():
            os.makedirs(join(args.output_dir, 'regions', region), exist_ok=True)
            if hasattr(viz, 'visualization'):
                viz = viz.visualization
            viz.save(join(args.output_dir, region, name))

    for region, data in taxa_viz_region.items():
        for name, viz in data.items():
            if hasattr(viz, 'visualization'):
                viz = viz.visualization
            os.makedirs(join(args.output_dir, 'regions', region), exist_ok=True)
            viz.save(join(args.output_dir, 'regions', region, name))

    for name, viz in summary.items():
        if hasattr(viz, 'visualization'):
            viz = viz.visualization
        viz.save(join(args.output_dir, name))


if __name__ == '__main__':
    test = False
    parser = get_parser()
    args = parser.parse_args()
    args.classifier_dir  = os.path.abspath(args.classifier_dir)
    primers = PRIMERS[args.libprep]
    if args.regions is None or args.regions == 'None':
        args.regions = list(primers.keys())
    else:
        args.regions = args.regions.split(',')

    if os.path.exists(args.sample_info):
        samples = Metadata.load(args.sample_info)

    # adata key: region, value: SampleData[PairedEndSequencesWithQuality] artifact
    adata = demultiplex_manifests(args.input, args.regions, args.libprep, split_on_header=True, threads=args.threads)

    counts, merged_counts = sequence_counts(adata, min_count=args.filter_region_count )
    # filter regions with too few reads
    for k in list(adata.keys()):
        if not k in counts:
            del adata[k]

    # denoise dada2
    tables, sequences, stats = denoise_dada2(adata, threads=args.threads)
    denoise_viz_region = dada2_summary(tables, sequences, stats)

    # classify sequences
    taxas = taxonomy_classify(sequences, args.classifier_dir, primers, level='99', threads=args.threads)
    taxa_viz_region = taxonomy_summary(taxas, tables, samples)

    # merge data
    table, taxonomy, sequence, meta_region = merge_data(tables, taxas, sequences, samples)

    # filter features
    table, taxonomy, sequence = filter_features(table, taxonomy, sequence, db=args.taxonomy_db, min_confidence=args.min_confidence)

    # table summaries
    summary = summary_data(table, taxonomy, sequence, samples)

    # biom data
    biom_table = create_biom(table, taxonomy, sequence, features_meta=meta_region, samples_meta=samples)

    # diversity
    # diversity_region = calc_diversity_region(tables, sample_meta=samples, max_depth=5000)

    write_data(table, taxonomy, sequence, adata, biom_table, denoise_viz_region, taxa_viz_region, summary)

    # phylogenetic tree
    if args.build_tree:
        tree = build_phylogenetic_tree(sequence, threads=args.threads)
        tree.rooted_tree.save(join(args.output_dir, 'tree'))
