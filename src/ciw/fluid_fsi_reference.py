"""Independent continuous coupled-eigenmode reference, no FV matrices/recurrence.

The characteristic boundary equation is bracketed independently. Elevation
observations are analytical cell averages; velocities are exact face values.
This establishes the continuum linear benchmark only, not a physical experiment.
"""
import math

from .control_contracts import number
from .fluid_fsi_contract import validate_request

REFERENCE_ID="independent_continuous_compliant_wall_characteristic_mode_binary64.v1"


def reference(request,times,cell_x_m,face_x_m):
    request=validate_request(request)
    if type(times) is not list or not 1<=len(times)<=257 or type(cell_x_m) is not list or not 1<=len(cell_x_m)<=256:
        raise ValueError("Reference time/space arrays exceed the bounded continuum benchmark")
    if type(face_x_m) is not list or len(face_x_m)!=len(cell_x_m)+1:
        raise ValueError("Reference requires enclosing ordered faces for cell averages")
    model,wall=request["model"],request["structure"]
    length=model["length_m"];depth=model["depth_m"];width=model["width_m"]
    density=model["density_kg_per_m3"];gravity=model["gravity_m_per_s2"]
    times=[number(t) for t in times];faces=[number(x) for x in face_x_m];centers=[number(x) for x in cell_x_m]
    if any(t<0 or t>request["integration"]["duration_s"] for t in times) or any(b<a for a,b in zip(times,times[1:])):
        raise ValueError("Reference times escape the synthetic model clock")
    if faces[0]!=0.0 or faces[-1]!=length or any(b<=a for a,b in zip(faces,faces[1:])):
        raise ValueError("Reference faces must partition the closed channel")
    if any(not math.isclose(center,(left+right)/2,rel_tol=0,abs_tol=1e-13*length) for center,left,right in zip(centers,faces,faces[1:])):
        raise ValueError("Reference centers must identify face-enclosed cell averages")
    # Independent dimensional form of the continuum characteristic equation.
    lower,upper=1e-12/length,math.pi/length
    for _ in range(100):
        k=(lower+upper)/2
        omega_squared=gravity*depth*k*k
        characteristic=(wall["mass_kg"]*omega_squared-wall["stiffness_n_per_m"])*math.sin(k*length)-density*gravity*width*depth*depth*k*math.cos(k*length)
        if characteristic>0: upper=k
        else: lower=k
    k=(lower+upper)/2
    omega=math.sqrt(gravity*depth)*k
    amplitude=model["amplitude_m"]
    wall_coefficient=-amplitude*math.sin(k*length)/(depth*k)
    mean_shapes=[(math.sin(k*right)-math.sin(k*left))/(k*(right-left)) for left,right in zip(faces,faces[1:])]
    result={"method":REFERENCE_ID,"wavenumber_per_m":k,"angular_frequency_per_s":omega,
            "characteristic_relative_residual":abs((wall["mass_kg"]*omega*omega-wall["stiffness_n_per_m"])*math.sin(k*length)-density*gravity*width*depth*depth*k*math.cos(k*length))/max(wall["stiffness_n_per_m"],1e-30),
            "time_s":times,"cell_x_m":centers,"face_x_m":faces,
            "free_surface_elevation_m":[],"depth_averaged_velocity_m_per_s":[],"wall_displacement_m":[],
            "wall_velocity_m_per_s":[],"boundary_elevation_m":[],"fluid_force_on_structure_n":[]}
    for time in times:
        cosine,sine=math.cos(omega*time),math.sin(omega*time)
        result["free_surface_elevation_m"].append([amplitude*shape*cosine for shape in mean_shapes])
        result["depth_averaged_velocity_m_per_s"].append([amplitude*omega/(depth*k)*math.sin(k*position)*sine for position in faces])
        result["wall_displacement_m"].append(wall_coefficient*cosine)
        result["wall_velocity_m_per_s"].append(-wall_coefficient*omega*sine)
        boundary=amplitude*math.cos(k*length)*cosine
        result["boundary_elevation_m"].append(boundary)
        result["fluid_force_on_structure_n"].append(density*gravity*width*depth*boundary)
    return result
