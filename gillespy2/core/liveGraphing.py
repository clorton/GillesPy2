def print_text_header(model):
    print("Time      |", end="")
    for species in model.listOfSpecies:
        print(species[:10].ljust(10), end="|")
    print("")

def display(display_type,solver):

    print("got solver of type",type(solver))

    if display_type is not None:
        # import gillespy2.solvers.numpy.basic_tau_hybrid_solver as solver
        from gillespy2.core.results import common_rgb_values

        import matplotlib.pyplot as plt
        from IPython.display import clear_output

        # try:

        if display_type == "text":

            print(str(round(solver.curr_time, 2))[:10].ljust(10), end="|")

            for i in range(solver.number_species):
                print(str(solver.curr_state[solver.species[i]])[:10].ljust(10), end="|")
            print("")

        elif display_type == "progress":

            clear_output(wait=True)
            print("progress =", round((solver.curr_time / solver.timeline.size) * 100, 2), "%\n")

        elif display_type == "graph":

            clear_output(wait=True)
            plt.figure(figsize=(18, 10))
            plt.xlim(right=solver.timeline.size)
            for i in range(solver.number_species):
                line_color = common_rgb_values()[(i) % len(common_rgb_values())]

                plt.plot(solver.trajectory_base[0][:, 0][:solver.entry_count].tolist(),
                         solver.trajectory_base[0][:, i + 1][:solver.entry_count].tolist(), color=line_color,
                         label=solver.species[i])

            plt.legend(loc='upper right')
            plt.show()

