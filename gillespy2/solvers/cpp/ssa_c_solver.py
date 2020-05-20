import gillespy2
from gillespy2.core import Model, Reaction, gillespyError, GillesPySolver, log
from gillespy2.solvers.utilities import solverutils as cs
import signal, time #for solver timeout implementation
import os #for getting directories for C++ files
import shutil #for deleting/copying files
import subprocess #For calling make and executing c solver
import inspect #for finding the Gillespy2 module path
import tempfile #for temporary directories
import numpy as np

GILLESPY_PATH = os.path.dirname(inspect.getfile(gillespy2))
GILLESPY_C_DIRECTORY = os.path.join(GILLESPY_PATH, 'solvers/cpp/c_base')

def _write_constants(outfile, model, reactions, species, parameter_mappings):
    outfile.write("const double V = {};\n".format(model.volume))
    outfile.write("std :: string s_names[] = {");
    if len(species) > 0:
        #Write model species names.
        for i in range(len(species)-1):
            outfile.write('"{}", '.format(species[i]))
        outfile.write('"{}"'.format(species[-1]))
        outfile.write("};\nunsigned int populations[] = {")
        #Write initial populations.
        for i in range(len(species)-1):
            outfile.write('{}, '.format(int(model.listOfSpecies[species[i]].initial_value)))
        outfile.write('{}'.format(int(model.listOfSpecies[species[-1]].initial_value)))
        outfile.write("};\n")
    if len(reactions) > 0:
        #Write reaction names
        outfile.write("std :: string r_names[] = {")
        for i in range(len(reactions)-1):
            outfile.write('"{}", '.format(reactions[i]))
        outfile.write('"{}"'.format(reactions[-1]))
        outfile.write("};\n")
    for param in model.listOfParameters:
        outfile.write("const double {0} = {1};\n".format(parameter_mappings[param], model.listOfParameters[param].value))

class SSACSolver(GillesPySolver):
    name = "SSACSolver"
    """TODO"""
    def __init__(self, model=None, output_directory=None, delete_directory=True):
        super(SSACSolver, self).__init__()
        self.__compiled = False
        self.delete_directory = False
        self.model = model
        if self.model is not None:
            # Create constant, ordered lists for reactions/species/
            self.species_mappings = self.model.sanitized_species_names()
            self.species = list(self.species_mappings.keys())
            self.parameter_mappings = self.model.sanitized_parameter_names()
            self.parameters = list(self.parameter_mappings.keys())
            self.reactions = list(self.model.listOfReactions.keys())

            if isinstance(output_directory, str):
                output_directory = os.path.abspath(output_directory)
            
                if isinstance(output_directory, str):
                    if not os.path.isfile(output_directory):
                        self.output_directory = output_directory
                        self.delete_directory = delete_directory
                        if not os.path.isdir(output_directory):
                            os.makedirs(self.output_directory)
                    else:
                        raise gillespyError.DirectoryError("File exists with the same path as directory.")
            else:
                self.temporary_directory = tempfile.TemporaryDirectory()
                self.output_directory = self.temporary_directory.name
                
            if not os.path.isdir(self.output_directory):
                raise gillespyError.DirectoryError("Errors encountered while setting up directory for Solver C++ files.")
            cs._copy_files(self.output_directory,GILLESPY_C_DIRECTORY)
            self.__write_template()
            self.__compile()
        
    def __del__(self):
        if self.delete_directory and os.path.isdir(self.output_directory):
            shutil.rmtree(self.output_directory)
        
    def __write_template(self, template_file='SimulationTemplate.cpp'):
        # Open up template file for reading.
        with open(os.path.join(self.output_directory, template_file), 'r') as template:
            # Write simulation C++ file.
            template_keyword = "__DEFINE_"
            # Use same lists of model's species and reactions to maintain order
            with open(os.path.join(self.output_directory, 'UserSimulation.cpp'), 'w') as outfile:
                for line in template:
                    if line.startswith(template_keyword):
                        line = line[len(template_keyword):]
                        if line.startswith("CONSTANTS"):
                            _write_constants(outfile, self.model, self.reactions, self.species, self.parameter_mappings)
                        if line.startswith("PROPENSITY"):
                            cs._write_propensity(outfile, self.model, self.species_mappings, self.parameter_mappings, self.reactions)
                        if line.startswith("REACTIONS"):
                            cs._write_reactions(outfile, self.model, self.reactions, self.species)
                    else:
                        outfile.write(line)

    def __compile(self):
        # Use makefile.
        cleaned = subprocess.run(["make", "-C", self.output_directory, 'cleanSimulation'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        built = subprocess.run(["make", "-C", self.output_directory, 'UserSimulation'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if built.returncode == 0:
            self.__compiled = True
        else:
            raise gillespyError.BuildError("Error encountered while compiling file:\nReturn code: {0}.\nError:\n{1}\n{2}\n".format(built.returncode, built.stdout.decode('utf-8'),built.stderr.decode('utf-8')))

    def run(self=None, model=None, t=20, number_of_trajectories=1, timeout=0,
            increment=0.05, seed=None, debug=False, profile=False, show_labels=True, **kwargs):

        if self is None or self.model is None:
            self = SSACSolver(model)
        if len(kwargs) > 0:
            for key in kwargs:
                log.warning('Unsupported keyword argument to {0} solver: {1}'.format(self.name, key))
        
        unsupported_sbml_features = {
                        'Rate Rules': len(model.listOfRateRules),
                        'Assignment Rules': len(model.listOfAssignmentRules), 
                        'Events': len(model.listOfEvents),
                        'Function Definitions': len(model.listOfFunctionDefinitions)
                        }
        detected_features = []
        for feature, count in unsupported_sbml_features.items():
            if count:
                detected_features.append(feature)

        if len(detected_features):
                raise gillespyError.ModelError(
                'Could not run Model.  SBML Feature: {} not supported by SSACSolver.'.format(detected_features))

        if self.__compiled:
            self.simulation_data = None
            number_timesteps = int(round(t/increment + 1))
            # Execute simulation.
            args = [os.path.join(self.output_directory, 'UserSimulation'), '-trajectories', str(number_of_trajectories), '-timesteps', str(number_timesteps), '-end', str(t)]
            if seed is not None:
                if isinstance(seed, int):
                    args.append('-seed')
                    args.append(str(seed))
                else:
                    seed_int = int(seed)
                    if seed_int > 0:
                        args.append('-seed')
                        args.append(str(seed_int))
                    else:
                        raise ModelError("seed must be a positive integer")

            #begin subprocess c simulation with timeout (default timeout=0 will not timeout)
            with subprocess.Popen(args, stdout=subprocess.PIPE, preexec_fn=os.setsid) as simulation:
                return_code = 0
                try:
                    if timeout > 0:
                        stdout, stderr = simulation.communicate(timeout=timeout)
                    else:
                        stdout, stderr = simulation.communicate()
                    return_code = simulation.wait()
                except subprocess.TimeoutExpired:
                        os.killpg(simulation.pid, signal.SIGINT) #send signal to the process group
                        stdout, stderr = simulation.communicate()
                        return_code = 33

            self.simulation_data, return_code = cs.c_solver_results(return_code,stdout,
                                                                 number_of_trajectories,number_timesteps,self,show_labels)

        return self.simulation_data, return_code

