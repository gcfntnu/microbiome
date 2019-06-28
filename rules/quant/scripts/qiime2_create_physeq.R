#!/usr/bin/env Rscript
args = commandArgs(trailingOnly=TRUE)

suppressWarnings(library(phyloseq))

biom.fn <- args[1]
tree.fn <- args[2]
out.fn <- args[3]

OTU <- import_biom(biom.fn, parseFunction=parse_taxonomy_default, treefilename=tree.fn)
TAX <- tax_table(OTU)
tax.names <- c("Kingdom","Phylum","Class","Order","Family","Genus","Species")[1:length(colnames(TAX))]
colnames(tax_table(OTU)) <- tax.names

saveRDS(OTU, out.fn)
