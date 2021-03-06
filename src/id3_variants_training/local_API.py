import vcf
import json


class LOCAL_API:
    def __init__(self, file_path, conf_matrix=False):
        """
        Initializes the API class

        NOTE:
            api_variant_list, api_indiv_list, and api_popu_list should be of the same
            length and every element in this list corresponds to a particular person

        Args:
            file_path (str): Path to json file that contains the variant rangess
            conf_matrix (bool): Initializes API to perform conf_matrix operations

        Attributes:
            variant_list (list): Represents the variants in each person. 
                                     The value of the variants is a list of 0's and 
                                     1's indicating if the variant exists in the person.
            indiv_list (list): Represents the individual code of a person
            popu_list (list): Represents the ancestry of the person
            variant_name_list (list): Names of the variants in the format of
                                          "VARIANT_POS,VARIANT_REF,VARIANT_ALT"
                                          "CHROMOSOME_#:START_POS:END_POS" (TODO - UPDATE TO THIS)
            ancestry_dict (dict): a dictionary which maps indivdual ID to population
            ancestry_list (list): A unique list of all the ancestries of people
            is_conf_matrix (bool): tells API to initialize the API for confusion matrix operations

        """
        with open(file_path) as f:
            self.config = json.load(f)
        self.variant_list = []
        self.indiv_list = []
        self.popu_list = []

        self.variant_name_list = []
        self.ancestry_dict = {}
        self.ancestry_list = []

        self.is_conf_matrix = conf_matrix

        # fetch variants from vcf and create a dictionary
        self.variants = self.fetch_variants()
        self.variant_dict = self.create_variant_dict(self.variants)

        # updates variables
        self.read_user_mappings(self.variant_dict)

    def fetch_variants(self):
        """
        Fetches the variants from the 1000 genomes VCF files and loads them into a variant_list

        Args:
            file_path (str): Path to json file that contains the variant rangess

        Returns:
            variant_list (list): a list of variants from the VCF file
        """
        variant_list = []
        for var_range in self.config['variant_ranges']:
            vcf_path = self.config['chr_paths'][str(var_range['chr'])]
            vcf_reader = vcf.Reader(open(str(vcf_path), 'rb'))
            variants = vcf_reader.fetch(int(var_range['chr']), int(var_range['start']), int(var_range['end']))
            variant_list.extend([variant for variant in variants])
        return variant_list

    @staticmethod
    def create_split_path(split_path, new_variant_name):
        """
        Creates two new split paths given the variant name and the split path

        Args:
            split_path (list1, list2): 
                This is the paths of the splits before the current split. The first list
                is the list of variant names and the second list is the direction
                of the split. The direction of the second list is depicted by 1's
                and 0's. Where 1 is splitting in the direction with the variant
                and 0 is splitting in the direction without the variant. 
            new_variant_name (str): unique id of variant

        Returns:
            w_split_path: The split path with the variant
            wo_split_path: The split path without the variant

        """
        w_split_path = (list(split_path[0]), list(split_path[1]))
        wo_split_path = (list(split_path[0]), list(split_path[1]))
        w_split_path[0].append(new_variant_name)
        wo_split_path[0].append(new_variant_name)
        w_split_path[1].append(1)
        wo_split_path[1].append(0)

        return w_split_path, wo_split_path

    def create_variant_dict(self, variants):
        """
        Creates a ditionary of variants from a vcf file which is used to update variables
        within this class

        Args:
            variants (Reader): A Reader Object from the PyVCF library which contains variants

        Returns:
            variant_dict (dict): A dictionary where the
                                    key: is the individual ID
                                    value: is a list of binary values where
                                           (1 = variant exists, 0 = variant doesn't exist)
        """
        variant_dict = {}
        idx = 0
        # loops through variants
        for variant in variants:
            idx += 1
            self.variant_name_list.append(':'.join([str(variant.CHROM), str(variant.POS-1), str(variant.POS)]))
            # loops through people in variants
            for call in variant.samples:
                variant_dict[call.sample] = variant_dict.get(call.sample, [])
                # checks if variant exists in person
                if call['GT'] in ['0/0', '0|0', '.']:
                    variant_dict[call.sample].append(0)
                else:
                    variant_dict[call.sample].append(1)
        return variant_dict

    def read_user_mappings(self, variant_dict):
        """
        Reads the usermappings from a file and updates the variables in the class
        """
        user_mapping_path = self.config['user_mapping_path']
        with open(user_mapping_path) as file:
            next(file)
            for line in file:
                split_line = line.split('\t')
                indiv_id = split_line[1]
                population = split_line[6]

                self.ancestry_dict[indiv_id] = population

                # checks if variant individual is in the variant dict from the vcf file
                if indiv_id in variant_dict:
                    self.indiv_list.append(indiv_id)
                    self.popu_list.append(population)
                    self.variant_list.append(variant_dict[indiv_id])

        self.ancestry_list = list(set(self.ancestry_dict.values()))
        self.ancestry_list.sort()


    def find_ignore_rows(self, split_path):
        """
        Find rows in the variant_list to ignore. This function
        is mainly used to filter the variant_list so "queries" can
        be made

        Args:
            split_path (list1, list2): 
                This is the paths of the splits before the current split. The first list
                is the list of variant names and the second list is the direction
                of the split. The direction of the second list is depicted by 1's
                and 0's. Where 1 is splitting in the direction with the variant
                and 0 is splitting in the direction without the variant.

        Returns:
            ignore_rows_idx (list): a list of numbers that represent the indices in the
                variant_list.
        """
        ignore_rows_idxs = []

        # basically find rows to ignore because it has been split upon already
        for exc_var, direction in zip(split_path[0], split_path[1]):
            # finding rows to ignore
            var_idx = self.variant_name_list.index(exc_var)
            # looping through all the people
            for idx, variants in enumerate(self.variant_list):
                if idx not in ignore_rows_idxs and variants[var_idx] is not direction:
                    ignore_rows_idxs.append(idx)

        return ignore_rows_idxs

    # splits the set given a variant 
    # returns 2 subsets of the data
    def split_subset(self, node, split_var=None):
        """
        Splits the subset given the path of the splits before and a
        variable to split on.

        Attributes:
            split_path (list1, list2): 
                This is the paths of the splits before the current split. The first list
                is the list of variant names and the second list is the direction
                of the split. The direction of the second list is depicted by 1's
                and 0's. Where 1 is splitting in the direction with the variant
                and 0 is splitting in the direction without the variant.
            split_var (string): The variant name it is now splitting on

        Returns:
            w_variant_dict (dict): The split subset that includes the variant
            wo_variant_dict (dict): The split subset that does not include the variant
            

        """
        split_path = node.split_path
        # retrieves variant from "API"
        ancestry_list = self.ancestry_list

        w_variant_dict = dict.fromkeys(ancestry_list, 0)
        wo_variant_dict = dict.fromkeys(ancestry_list, 0)

        ignore_rows_idxs = self.find_ignore_rows(split_path)

        # create new subset after finding all the rows to ignore
        for idx, variants in enumerate(self.variant_list):
            if idx in ignore_rows_idxs:
                continue
            popu = self.popu_list[idx]
            # check if split_var is null
            if split_var:
                f_var_idx = self.variant_name_list.index(split_var)
                if variants[f_var_idx] == 1:
                    w_variant_dict[popu] += 1
                else:
                    wo_variant_dict[popu] += 1

        return w_variant_dict, wo_variant_dict

    def find_next_variant_counts(self, split_path):
        """
        Finds the counts of the a potential next variant to perform the
        split on

        Attributes:
            split_path (list1, list2): 
                This is the paths of the splits before the current split. The first list
                is the list of variant names and the second list is the direction
                of the split. The direction of the second list is depicted by 1's
                and 0's. Where 1 is splitting in the direction with the variant
                and 0 is splitting in the direction without the variant.
        Returns:
            w_variant_list: 
                A list representing of a dictionary of ancestry counts per variant
                [
                    {'GBR': 5, 'CML': 0, 'ABC': 3 ...}
                    ...
                    ..
                    .
                ]
        """
        ancestry_list = self.ancestry_list
        w_variant_list = [dict.fromkeys(ancestry_list, 0) for variant_names in self.variant_name_list]
        ignore_rows_idxs = self.find_ignore_rows(split_path)

        for idx, variants in enumerate(self.variant_list):
            if idx in ignore_rows_idxs:
                continue
            popu = self.popu_list[idx]
            # find counts of variants
            for idx2, variant in enumerate(variants):
                if variant == 1:
                    w_variant_list[idx2][popu] += 1

        return w_variant_list

    def get_target_set(self):
        """
        Gets the target subset, which is the ancestry counts every variant

        Returns:
            counts (dict): A dictionary containing keys of ancestries and values of the counts for the particular ancestry
        """
        ancestry_list = self.ancestry_list
        counts = dict.fromkeys(ancestry_list, 0)
        for i in self.popu_list:
            counts[i] = counts.get(i, 0) + 1
        return counts

    def count_variants(self):
        """
        Gets the counts of each variant
        """
        my_dict = {}
        for variants in (self.variant_list):
            for idx, variant in enumerate(variants):
                if variant == 1:
                    my_dict[self.variant_name_list[idx]] = my_dict.get(self.variant_name_list[idx], 0) + 1
        return my_dict

if __name__ == "__main__":
    api = LOCAL_API('variant_ranges.json')
    print(api.variant_name_list)




