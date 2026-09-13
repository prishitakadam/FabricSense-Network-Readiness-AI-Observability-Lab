.PHONY: deploy experiment test destroy

deploy:
	sudo containerlab deploy --reconfigure -t st.clab.yml

experiment: deploy
	python3 -m fabric_readiness run

test:
	python3 -m unittest discover -s tests -v
	python3 -m compileall -q fabric_readiness

destroy:
	sudo containerlab destroy --cleanup -t st.clab.yml
