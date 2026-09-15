.PHONY: all deploy experiment test destroy

all: deploy experiment

deploy:
	sudo containerlab deploy --reconfigure -t st.clab.yml

experiment:
	python3 -m fabric_readiness run $(ARGS)

test:
	python3 -m unittest discover -s tests -v
	python3 -m compileall -q fabric_readiness mcp_servers

destroy:
	sudo containerlab destroy --cleanup -t st.clab.yml
